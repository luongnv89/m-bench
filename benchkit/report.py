"""Turn one or more result files into a Markdown report with mermaid charts.

The report is the deliverable: a table of every run, charts for accuracy and
cost, a per-task diff between the two most interesting runs, and the caveats
that keep the numbers honest.
"""
import json
import os

from . import runner, stats

BAR = "xychart-beta"

#: what a run that used benchkit's own tool loop, rather than a harness, is called
BUILTIN_HARNESS = "built-in loop"


def load(path):
    """Load a result file, naming the file on any parse failure."""
    try:
        with open(path) as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{os.path.basename(path)}: {e}") from None
    d["_path"] = os.path.basename(path)
    return d


def with_cost(run):
    """The run, with per-task token and wall-clock cost filled in if it lacks it.

    Result files written before issue #86 carry no ``cost``/``cost_by_task``
    in their summary, but their ``results`` list still holds each generation's
    tokens and elapsed seconds, so the cost is rebuilt from that. A file with
    neither is returned unchanged and reports its cost as not recorded. Never
    mutates *run*.
    """
    s = run["summary"]
    if "cost_by_task" in s and "cost" in s:
        return run
    rows = [r for r in (run.get("results") or [])
            if isinstance(r, dict) and "task" in r]
    if not rows:
        return run
    s = dict(s, cost=runner.cost_summary(rows), cost_by_task=runner.cost_by_task(rows))
    return dict(run, summary=s)


def generations(s):
    """Generations behind a summary's rate: recorded, else tasks x samples, else None."""
    if s.get("generations"):
        return s["generations"]
    try:
        return int(s.get("tasks")) * int((s.get("config") or {}).get("samples"))
    except (TypeError, ValueError):
        return None


def efficiency(s):
    """Mean efficiency on solved tasks, from either the new or the legacy field."""
    e = s.get("efficiency")
    return e if e is not None else s.get("mean_efficiency")


def solve_ci(s):
    """95% Wilson interval of the solve rate, recomputed from the (pooled) counts.

    Never read back from the file: a pooled row must quote the interval of
    every generation behind it, not one member's.
    """
    return stats.rate_interval(s.get("pass_at_1"), generations(s))


def _rank_value(s):
    """The one ruler every ranking, bold and pairing uses (issue #86).

    Solve rate decides; efficiency only breaks exact ties. Efficiency used to
    be multiplied in (the agent score), which let call counts -- counted
    differently by every harness, against an oracle par -- outrank solving.
    """
    return (s.get("pass_at_1") or 0, efficiency(s) or 0)


#: summary counters that add up across re-runs
_SUMMED = ("generations", "truncated", "errored", "total_tool_calls", "malformed_args",
           "unknown_tools", "hit_turn_limit", "stalled_no_tool_call",
           "total_input_tokens")
#: per-generation means, pooled weighted by each re-run's generation count
_PER_GENERATION = ("mean_completion_tokens", "mean_tok_s", "mean_ttft", "mean_turns",
                   "mean_tool_calls", "mean_par_calls", "mean_input_tokens",
                   "mean_reasoning_tokens")
#: per-suite-execution figures: a pooled row reports the mean re-run
_PER_RUN = ("wall_seconds", "aggregate_tok_s")


def _group_key(run):
    """What two result files must share to be samples of one run, or None.

    The label names the run and ``suite_hash`` (issue #88) proves both files
    scored the same tasks the same way. The setup fields are a guard on top: a
    custom label reused for a different harness, thinking mode, model or
    serving config is a collision, not a re-run, and pooling it would straddle
    the ranking blocks. A file without ``suite_hash`` (``schema_version`` 0)
    cannot prove it ran the same tasks, so it is never grouped.
    """
    s = run["summary"]
    h = s.get("suite_hash")
    if not h:
        return None
    cfg = s.get("config") or {}
    st = _setup_of(run)
    extra = json.dumps(cfg.get("extra") or {}, sort_keys=True, default=str)
    return (_label(run), h, s.get("kind"), st["harness"], st["thinking"],
            st["config"], st["model"], cfg.get("max_tokens"),
            cfg.get("temperature"), extra, _endpoint(s))


def group_runs(runs):
    """Group re-runs of one label into samples of one run. Pure; never mutates.

    Re-running with the same label writes ``<label>.1.json``, ``<label>.2.json``
    next to the first file; those are more samples of the same run, not new
    runs. Returns ``[{"key", "label", "suite_hash", "members": [run, ...]}]`` in
    first-appearance order. Files lacking ``suite_hash`` each form their own
    group (``key`` None): pooling a file whose task set cannot be proven equal
    would silently mix suites.
    """
    groups, index = [], {}
    for r in runs:
        key = _group_key(r)
        if key is not None and key in index:
            groups[index[key]]["members"].append(r)
            continue
        if key is not None:
            index[key] = len(groups)
        groups.append(dict(key=key, label=_label(r),
                           suite_hash=r["summary"].get("suite_hash"), members=[r]))
    return groups


def unhashed_label_collisions(runs):
    """Labels shared by several files that predate ``suite_hash`` (kept separate)."""
    seen = {}
    for r in runs:
        if not r["summary"].get("suite_hash"):
            seen[_label(r)] = seen.get(_label(r), 0) + 1
    return sorted(label for label, n in seen.items() if n > 1)


def _weighted(members, key, weights):
    pairs = [(m[key], w) for m, w in zip(members, weights)
             if m.get(key) is not None and w]
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else None


def _pool_cost(costs, count_key):
    """Pool cost blocks: tokens weighted by generations that reported them."""
    costs = [c for c in costs if c]
    if not costs:
        return None
    reported = [c.get("tokens_reported") or 0 for c in costs]
    counts = [c.get(count_key) or 0 for c in costs]
    return {count_key: sum(counts), "tokens_reported": sum(reported),
            "input_tokens": _weighted(costs, "input_tokens", reported),
            "output_tokens": _weighted(costs, "output_tokens", reported),
            "seconds": _weighted(costs, "seconds", counts)}


def pool(group):
    """One run dict whose summary pools a group's re-runs; inputs are untouched.

    Rates are weighted by generations and ``by_task`` by samples per task, so
    pooled ``pass_at_1`` equals the rate over every generation of every re-run.
    ``config.samples`` and ``generations`` are summed, which is what makes the
    confidence interval quoted beside the row cover the pooled sample count. Figures
    that describe one suite execution (wall-clock) are the mean re-run. Stats
    that cannot be rebuilt from summaries alone (medians, all/any-sample pass)
    are ``None``.
    """
    members = group["members"]
    if len(members) == 1:
        return members[0]
    S = [m["summary"] for m in members]
    gens = [s.get("generations") or 0 for s in S]
    samples = [(s.get("config") or {}).get("samples") or 0 for s in S]
    first = S[0]

    pooled = {k: first[k] for k in ("kind", "tasks", "suite_hash", "schema_version",
                                    "harness") if k in first}
    pooled["config"] = dict(first["config"], samples=sum(samples) or None)
    for k in _SUMMED:
        if any(k in s for s in S):
            pooled[k] = sum(s.get(k) or 0 for s in S)
    for k in _PER_GENERATION:
        if any(k in s for s in S):
            pooled[k] = _weighted(S, k, gens)
    for k in _PER_RUN:
        if any(k in s for s in S):
            pooled[k] = _weighted(S, k, [1] * len(S))
    pooled["median_completion_tokens"] = None
    pooled["pass_all_samples"] = pooled["pass_any_sample"] = None
    pooled["pass_at_1"] = _weighted(S, "pass_at_1", gens) or 0.0

    tasks = sorted({t for s in S for t in (s.get("by_task") or {})})
    pooled["by_task"] = {t: _weighted([s.get("by_task") or {} for s in S], t, samples)
                         for t in tasks}
    pooled["by_difficulty"] = {
        d: _weighted([s.get("by_difficulty") or {} for s in S], d, gens)
        for d in ("easy", "medium", "hard")}

    if "valid_call_rate" in first:
        pooled["valid_call_rate"] = _weighted(
            S, "valid_call_rate", [s.get("total_tool_calls") or 0 for s in S])
    if "mean_efficiency" in first:
        # efficiency is averaged over solved generations only
        solved = [(s.get("pass_at_1") or 0) * g for s, g in zip(S, gens)]
        pooled["mean_efficiency"] = _weighted(S, "mean_efficiency", solved)
    if "agent_score" in first:
        pooled["agent_score"] = (None if any(s.get("agent_score") is None for s in S)
                                 else pooled["pass_at_1"]
                                 * (pooled.get("mean_efficiency") or 0.0))

    # the separate headline numbers (#86/#87), recomputed over every sample
    pooled["solve_rate"] = pooled["pass_at_1"]
    ci = stats.rate_interval(pooled["pass_at_1"], pooled.get("generations"))
    pooled["solve_rate_ci"] = list(ci) if ci else None
    if any(efficiency(s) is not None for s in S):
        solved = [(s.get("pass_at_1") or 0) * g for s, g in zip(S, gens)]
        pooled["efficiency"] = _weighted([dict(e=efficiency(s)) for s in S], "e", solved)
    if any(s.get("cost") for s in S):
        pooled["cost"] = _pool_cost([s.get("cost") for s in S], "generations")
    if any(s.get("cost_by_task") for s in S):
        cost_tasks = sorted({t for s in S for t in (s.get("cost_by_task") or {})})
        pooled["cost_by_task"] = {
            t: _pool_cost([(s.get("cost_by_task") or {}).get(t) for s in S], "samples")
            for t in cost_tasks}

    # solve rate ranks, so it is what each re-run is quoted on
    return dict(summary=pooled, _path=members[0]["_path"],
                _members=[m["_path"] for m in members],
                _member_metric="pass_at_1",
                _member_scores=[s.get("pass_at_1") or 0.0 for s in S])


def _label(run):
    cfg = run["summary"]["config"]
    if cfg.get("label"):
        return cfg["label"]
    return f"{cfg['model']} think-{'ON' if cfg['thinking'] else 'OFF'} {cfg['max_tokens']//1000}k"


def _short(run, label):
    """A chart-axis label that still distinguishes runs after truncation."""
    cfg = run["summary"]["config"]
    model = (cfg.get("served_model_id") or cfg.get("model") or "").split("/")[-1]
    model = model.replace("-NVFP4", "").replace("-A3B", "").replace("-Instruct", "")
    stem = model or label.split()[0]
    if len(stem) > 12:
        stem = stem[:12]
    return f"{stem} {'ON' if cfg.get('thinking') else 'OFF'}"


def _fmt(v, pct=False, digits=1):
    if v is None:
        return "—"
    if pct:
        return f"{v * 100:.{digits}f} %"
    if isinstance(v, float):
        return f"{v:,.{digits}f}"
    return f"{v:,}"


def _chart(title, y_label, categories, values, y_max=None, kind="bar"):
    if y_max is None:
        mx = max(values) if values else 0
        y_max = mx * 1.15 if mx else 1
    cats = ", ".join(f'"{c}"' for c in categories)
    vals = ", ".join(f"{v:.4g}" for v in values)
    return (f"```mermaid\n{BAR}\n"
            f'    title "{title}"\n'
            f"    x-axis [{cats}]\n"
            f'    y-axis "{y_label}" 0 --> {y_max:.4g}\n'
            f"    {kind} [{vals}]\n```\n")


def _setup_of(run):
    """The (harness, thinking, config, model) a run came from, best-effort.

    `bench sweep` records the serving config and harness on the run config, so
    a swept result is fully attributed. Older result files predate those fields
    and fall back to whatever the harness block recorded, then to the built-in
    loop -- an unlabelled row is still reported, just as "not recorded".
    """
    s = run["summary"]
    cfg = s["config"]
    # harness.describe() emits "harness" (base.py/opencode.py/pi.py/claudecode.py),
    # not "name" -- reading the wrong key here would file every legacy harness
    # run under the built-in loop and rank three harnesses inside one block.
    block = s.get("harness") or {}
    harness = cfg.get("harness") or block.get("harness") or block.get("name") \
        or BUILTIN_HARNESS
    return dict(
        harness=harness,
        thinking=bool(cfg.get("thinking")),
        config=cfg.get("serving_config") or "not recorded",
        # a swept row that deliberately used the live launcher says so; only a
        # file that never recorded the field at all is "not recorded"
        model=cfg.get("served_model_id") or cfg.get("model") or "?",
        samples=cfg.get("samples"),
    )


def _blocks(runs):
    """{(harness, thinking): [run index, ...]} — the only comparable groupings.

    One harness in one thinking mode. Everything that names a winner, bolds a
    row or pairs two runs against each other has to respect this boundary, or
    the report crowns the harness instead of the setup.
    """
    blocks = {}
    for i, r in enumerate(runs):
        st = _setup_of(r)
        blocks.setdefault((st["harness"], st["thinking"]), []).append(i)
    return blocks


def _setup_short(runs):
    """Chart-axis labels for a sweep, keyed on the axes a sweep actually varies.

    `_short` keys on the model, which is exactly what a sweep holds constant —
    it would render three different setups as three identical bars.
    """
    out = []
    for r in runs:
        st = _setup_of(r)
        harness = "builtin" if st["harness"] == BUILTIN_HARNESS else st["harness"]
        cfg = st["config"]
        cfg = "active" if cfg.startswith("(active") else (
            "?" if cfg == "not recorded" else cfg)
        out.append(f"{harness[:7]} {cfg[:8]} {'ON' if st['thinking'] else 'OFF'}")
    # suffix *every* occurrence of a repeated label, not just the first: a
    # chart axis reading "opencod cfg-a OFF" twice names neither run.
    totals = {label: out.count(label) for label in set(out)}
    seen = {}
    for i, label in enumerate(out):
        if totals[label] > 1:
            seen[label] = seen.get(label, 0) + 1
            out[i] = f"{label} {seen[label]}"
    return out


def _pts(v):
    return f"{v * 100:+.1f}"


def _ci_cell(s):
    """``62.5 % (41–80)`` -- the solve rate and its 95% interval, in points."""
    rate = _fmt(s.get("pass_at_1"), pct=True)
    ci = solve_ci(s)
    if not ci:
        return f"{rate} (CI n/a)"
    return f"{rate} ({ci[0] * 100:.0f}–{ci[1] * 100:.0f})"


def margin_verdict(best, runner_up):
    """Is ``best`` really ahead of ``runner_up`` on solve rate? (issue #87)

    Replaces the fixed "~8 points is noise" rule, which was not derived from
    the data: the answer is the 95% Newcombe interval of the difference in
    solve rates, which widens and narrows with the generations actually behind
    each row. An interval that contains zero is a tie.
    """
    p1, p2 = best.get("pass_at_1") or 0, runner_up.get("pass_at_1") or 0
    d = stats.newcombe(p1, generations(best), p2, generations(runner_up))
    if d is None:
        return ("No confidence interval is available — a row does not record how "
                "many generations it ran — so this margin cannot be told from noise.")
    span = f"[{_pts(d[0])}, {_pts(d[1])}] points"
    if p1 == p2:
        return (f"Solve rates are equal (interval of the difference {span}); only "
                "efficiency separates them, and that is **a tie on solving** — "
                "re-run with more samples before acting on it.")
    if d[0] <= 0:
        return (f"The 95% interval of that difference is {span} and includes zero: "
                "**inside the noise** — treat it as a tie and re-run with more "
                "samples before acting on it.")
    return (f"The 95% interval of that difference is {span} and excludes zero, "
            "so it **clears the noise**.")


def rank_setups(runs, labels):
    """Markdown ranking setups *within* a comparable block, never across them.

    A block is one harness in one thinking mode. That boundary is not
    fastidiousness: this repo's own harness-spread campaign in `results/`
    records a swing on identical weights as large as a model change, so a table
    that ranks an opencode row above a built-in-loop row is reporting the
    harness, not the setup. Thinking and non-thinking are likewise two products, never
    two candidates for one crown. Inside a block the serving config and the
    model are the axes actually being compared, and there the winner is real --
    subject to the confidence interval of the margin, which every block states.
    """
    S = [r["summary"] for r in runs]
    setups = [_setup_of(r) for r in runs]
    blocks = _blocks(runs)

    out = ["## Ranked setups\n"]
    out.append("A setup is the serving config, the harness and the thinking mode "
               "together. Scores are ranked **within** one harness and one thinking "
               "mode and nowhere else: identical weights score materially "
               "differently through different harnesses — see the harness-spread "
               "campaign in `results/` — and thinking and non-thinking are two "
               "products, not two candidates. There is deliberately no single "
               "cross-harness winner below. Solve rate ranks; efficiency is shown "
               "beside it and only breaks exact ties.\n")

    for (harness, thinking), idx in blocks.items():
        ranked = sorted(idx, key=lambda i: tuple(-v for v in _rank_value(S[i])))
        out.append(f"### {harness} · thinking {'ON' if thinking else 'OFF'}\n")
        out.append("| Rank | Serving config | Model | Solved (95% CI) | Efficiency "
                   "| Samples |\n|---|---|---|---|---|---|")
        for rank, i in enumerate(ranked, 1):
            st = setups[i]
            cell = f"**{_ci_cell(S[i])}**" if rank == 1 else _ci_cell(S[i])
            name = f"**{labels[i]}**" if rank == 1 else labels[i]
            samples = st["samples"] if st["samples"] is not None else "not recorded"
            out.append(f"| {rank} | `{st['config']}` | {st['model']} — {name} "
                       f"| {cell} | {_fmt(efficiency(S[i]), pct=True)} | {samples} |")
        out.append("")
        best = ranked[0]
        if len(ranked) == 1:
            out.append(f"**Winner: {labels[best]}** — the only setup in this block, "
                       "so this is a measurement, not a comparison.\n")
            continue
        runner_up = ranked[1]
        pb, pr = (S[best].get("pass_at_1") or 0) * 100, (S[runner_up].get("pass_at_1") or 0) * 100
        verdict = (f"**Winner: {labels[best]}** — solved {pb:.1f} % against "
                   f"{pr:.1f} % for {labels[runner_up]}, "
                   f"a margin of {pb - pr:.1f} points. ")
        out.append(verdict + margin_verdict(S[best], S[runner_up]) + "\n")
    return "\n".join(out)


def _shared(values, short, fmt=str):
    """One cell for a setting the runs may or may not agree on.

    Silently printing run 0's value hides a methodology mismatch, so when the
    runs disagree the cell names every value in table order instead.
    """
    vals = list(values)
    if all(v == vals[0] for v in vals):
        return fmt(vals[0]), True
    return ("mixed — " + ", ".join(f"{fmt(v)} ({short[i]})"
                                   for i, v in enumerate(vals)), False)


def _endpoint(s):
    # harness runs record "(harness)" as the config base_url; the real endpoint
    # the adapter dialled lives on the harness block.
    url = s["config"]["base_url"]
    if url == "(harness)":
        url = (s.get("harness") or {}).get("base_url")
    if not url or url == "(harness)":
        return None
    # claude-code dials the Anthropic surface at the root and the others the
    # OpenAI-compatible /v1 on the same server; compare hosts, not surfaces.
    return url.rstrip("/").removesuffix("/v1")


def _endpoint_cell(eps, short):
    """The Setup table's endpoint row: one host when they agree, every host otherwise."""
    known = [(short[i], e) for i, e in enumerate(eps) if e]
    if not known:
        return "not recorded"
    if all(e == known[0][1] for _, e in known):
        endpoint = f"`{known[0][1]}`"
        if len(known) < len(eps):
            missing = ", ".join(short[i] for i, e in enumerate(eps) if not e)
            endpoint += f" (not recorded for {missing})"
        return endpoint
    return "mixed — " + ", ".join(f"`{e}` ({n})" for n, e in known)


def _setup_section(S, short):
    """The Setup table, plus the sample settings the caveats quote back."""
    eps = [_endpoint(s) for s in S]
    tasks, _ = _shared([s.get("tasks") for s in S], short)
    conc, conc_same = _shared([s["config"].get("concurrency") for s in S], short)
    samples, samples_same = _shared([s["config"].get("samples") for s in S], short)
    gens, _ = _shared([generations(s) for s in S], short)
    agentic = all(s.get("kind") == "agentic" for s in S)

    out = ["## Setup\n"]
    out.append("| | |\n|---|---|")
    out.append(f"| Endpoint | {_endpoint_cell(eps, short)} |")
    out.append(f"| Tasks | {tasks} |")
    if samples_same:
        out.append(f"| Samples per task | {samples} (⇒ {gens} generations per run) |")
    else:
        out.append(f"| Samples per task | {samples} |")
    out.append(f"| Concurrency | {conc} |")
    if agentic:
        out.append("| Metric | solve rate (predicate over the final workspace), with a "
                   "95% Wilson interval; efficiency reported separately |\n")
    else:
        out.append("| Metric | pass@1 over hidden executable unit tests, with a 95% "
                   "Wilson interval |\n")
    if not (conc_same and samples_same):
        out.append("<sub>The runs above were **not** all collected under the same settings. "
                   "Solve rate and tool-call counts are unaffected, but wall-clock is not "
                   "comparable across rows that differ in concurrency, and scores from "
                   "different sample counts carry wider or narrower intervals.</sub>\n")
    return out, samples, samples_same


def _tokens_cell(cost):
    """``12,345 in / 678 out`` per task, or why there is no number."""
    if not cost:
        return "not recorded"
    if not cost.get("tokens_reported"):
        return "not reported"
    cell = f"{_fmt(cost.get('input_tokens'), digits=0)} in / " \
           f"{_fmt(cost.get('output_tokens'), digits=0)} out"
    total = cost.get("generations", cost.get("samples"))
    if total and cost["tokens_reported"] < total:
        cell += f" ({cost['tokens_reported']}/{total} reported)"
    return cell


def _seconds_cell(cost):
    if not cost or cost.get("seconds") is None:
        return "not recorded"
    return f"{cost['seconds']:,.1f} s"


def _headline_section(S, labels, agentic):
    """Solve rate and efficiency as separate headline numbers, plus their cost (#86)."""
    out = ["## Headline\n"]
    if agentic:
        out.append("| Run | Solve rate (95% CI) | Efficiency | Tokens per task "
                   "| Time per task |\n|---|---|---|---|---|")
    else:
        out.append("| Run | pass@1 (95% CI) | Tokens per task | Time per task |\n"
                   "|---|---|---|---|")
    for s, label in zip(S, labels):
        cost = s.get("cost")
        eff = f" | {_fmt(efficiency(s), pct=True)}" if agentic else ""
        out.append(f"| {label} | {_ci_cell(s)}{eff} | {_tokens_cell(cost)} "
                   f"| {_seconds_cell(cost)} |")
    out.append("")
    notes = ["The bracket is the 95% Wilson interval of the solve rate, in points."]
    if agentic:
        notes.append("*Efficiency* = par tool calls / calls actually used, capped at 1, "
                     "on solved tasks only. It is reported beside the solve rate and "
                     "never multiplied into it: par comes from an oracle and harnesses "
                     "count calls differently, so it measures style as much as skill.")
    notes.append("*Tokens* and *time* are the mean per task attempt (input and output "
                 "tokens as the endpoint or harness reported them; wall-clock seconds).")
    if any((s.get("cost") or {}).get("tokens_reported") == 0 for s in S):
        notes.append("*not reported* = no usage was reported for those runs (a harness "
                     "that emits none, or a backend that drops it); recorded as null, "
                     "never as 0.")
    out.append("<sub>" + " ".join(notes) + "</sub>\n")
    return out


def _leaders(S, runs, setups):
    """Which rows the results table bolds: each block's leader in a sweep."""
    if setups:
        return {max(idx, key=lambda i: _rank_value(S[i]))
                for idx in _blocks(runs).values()}
    return {max(range(len(S)), key=lambda i: _rank_value(S[i]))}


def _results_section(runs, S, labels, setups):
    """The results table and its footnotes; also whether runs are agentic/scored."""
    agentic = all(s.get("kind") == "agentic" for s in S)
    # agentic runs predating oracle-par efficiency carry no agent_score; the
    # composite column is then left out rather than shown half-empty.
    scored = agentic and all(s.get("agent_score") is not None for s in S)
    leaders = _leaders(S, runs, setups)
    out = ["## Results\n"]
    if agentic:
        out.append("| Run | Solved | Efficiency | easy | medium | hard | Mean turns "
                   "| Mean calls | Par | Valid calls | Turn-limit | Wall"
                   + (" | Agent score |" if scored else " |") + "\n"
                   + "|---" * (13 if scored else 12) + "|")
    else:
        out.append("| Run | pass@1 | easy | medium | hard | Wall | Mean out tok "
                   "| Truncated | tok/s |\n|---|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(S):
        d = s.get("by_difficulty") or {}
        name = f"**{labels[i]}**" if i in leaders else labels[i]
        solved = _fmt(s["pass_at_1"], pct=True)
        solved = f"**{solved}**" if i in leaders else solved
        if agentic:
            row = (f"| {name} | {solved} | {_fmt(efficiency(s), pct=True)} "
                   f"| {_fmt(d.get('easy'), pct=True)} "
                   f"| {_fmt(d.get('medium'), pct=True)} | {_fmt(d.get('hard'), pct=True)} "
                   f"| {_fmt(s.get('mean_turns'))} | {_fmt(s.get('mean_tool_calls'))} "
                   f"| {_fmt(s.get('mean_par_calls'))} "
                   f"| {_fmt(s.get('valid_call_rate'), pct=True)} | {s.get('hit_turn_limit')} "
                   f"| {_fmt(s.get('wall_seconds'), digits=0)} s |")
            if scored:
                row += f" {s['agent_score'] * 100:.1f} |"
            out.append(row)
        else:
            out.append(f"| {name} | {solved} "
                       f"| {_fmt(d.get('easy'), pct=True)} "
                       f"| {_fmt(d.get('medium'), pct=True)} | {_fmt(d.get('hard'), pct=True)} " +
                       f"| {_fmt(s.get('wall_seconds'), digits=0)} s "
                       f"| {_fmt(s.get('mean_completion_tokens'), digits=0)} "
                       f"| {s.get('truncated')} | {_fmt(s.get('mean_tok_s'))} |")
    out.append("")
    if agentic:
        note = ("<sub>*Solved* ranks the runs; *Efficiency* is reported beside it and "
                "only breaks exact ties. *Par* is measured by running each task's "
                "oracle, so it does not depend on the model. *Valid calls* = calls that "
                "did not error. *Turn-limit* = runs abandoned without finishing.")
        if scored:
            note += (" *Agent score* = solved x efficiency, out of 100 — kept for "
                     "comparison with earlier reports; it no longer ranks.")
        out.append(note + "</sub>\n")

    if setups:
        out.append("<sub>Bold marks the leader **within** its own harness and thinking "
                   "mode — see *Ranked setups* below for the verdict. Rows from "
                   "different harnesses are not comparable, and neither are the "
                   "charts that follow.</sub>\n")
        out.append(rank_setups(runs, labels))
    return out, agentic, scored


def _cost_section(S, labels):
    """Per-task token and wall-clock cost, one column per run (issue #86)."""
    tables = [s.get("cost_by_task") or {} for s in S]
    tasks = sorted({t for tb in tables for t in tb})
    if not tasks:
        return []
    out = ["## Cost per task\n"]
    out.append("<sub>Mean per attempt: input / output tokens, then wall-clock "
               "seconds. *not reported* = no usage reported for that task; "
               "*–* = the run has no cost record for it.</sub>\n")
    out.append("| Task | " + " | ".join(labels) + " |\n" + "|---" * (len(labels) + 1) + "|")
    for t in tasks:
        cells = []
        for tb in tables:
            c = tb.get(t)
            if not c:
                cells.append("–")
                continue
            tok = ("not reported" if not c.get("tokens_reported") else
                   f"{_fmt(c.get('input_tokens'), digits=0)} / "
                   f"{_fmt(c.get('output_tokens'), digits=0)}")
            cells.append(f"{tok} · {_seconds_cell(c)}")
        out.append(f"| `{t}` | " + " | ".join(cells) + " |")
    out.append("")
    return out


def _charts_section(S, short, agentic):
    out = []
    out.append(_chart("Solve rate (%)" if agentic else "pass@1 (%)",
                      "solved %" if agentic else "pass@1 %", short,
                      [s["pass_at_1"] * 100 for s in S], y_max=100))
    out.append(_chart("Cost of that accuracy — suite wall-clock (s)", "seconds", short,
                      [s.get("wall_seconds") or 0 for s in S]))
    costs = [s.get("cost") or {} for s in S]
    # a 0 bar -- or an output-only bar beside input+output ones, from a file
    # that never recorded input -- would read as a measurement; chart tokens
    # only when every row has both sides
    if all(c.get("tokens_reported") and c.get("input_tokens") is not None
           and c.get("output_tokens") is not None for c in costs):
        out.append(_chart("Cost of that accuracy — tokens per task (in + out)", "tokens",
                          short, [c["input_tokens"] + c["output_tokens"] for c in costs]))
    if agentic:
        if all(efficiency(s) is not None for s in S):
            out.append(_chart("Efficiency on solved tasks (par / calls, %)", "%", short,
                              [efficiency(s) * 100 for s in S], y_max=100))
        out.append(_chart("Mean tool calls per task", "calls", short,
                          [s.get("mean_tool_calls") or 0 for s in S]))
        out.append(_chart("Valid tool-call rate (%)", "%", short,
                          [(s.get("valid_call_rate") or 0) * 100 for s in S], y_max=100))
    else:
        out.append(_chart("Mean output tokens per answer", "tokens", short,
                          [s.get("mean_completion_tokens") or 0 for s in S]))
    return out


def _difficulty_section(S, labels):
    """Accuracy by difficulty, one mermaid line per run."""
    diffs = ["easy", "medium", "hard"]
    lines = "\n".join(
        "    line [" + ", ".join(f"{(s['by_difficulty'].get(d) or 0) * 100:.4g}" for d in diffs) + "]"
        for s in S)
    out = ["```mermaid\n" + BAR + "\n"
           '    title "pass@1 by difficulty (%)"\n'
           '    x-axis ["easy", "medium", "hard"]\n'
           '    y-axis "pass@1 %" 0 --> 100\n' + lines + "\n```\n"]
    out.append("<sub>" + " · ".join(f"Line {i+1} = {line}" for i, line in enumerate(labels)) + "</sub>\n")
    return out


def _disagreement_section(runs, S, labels, setups):
    """Per-task disagreement between the best run and the runner-up.

    A head-to-head across harnesses or thinking modes is the cross-block
    comparison the ranking exists to forbid, so in a sweep the pair must come
    from one block -- and if no block holds two runs, there is no pair.
    The pair is selected using the *same* key the results table used to bold
    the winner, so the disagreement section never compares a pair excluding
    the declared winner.
    """
    pool = range(len(S))
    if setups:
        candidates = [idx for idx in _blocks(runs).values() if len(idx) >= 2]
        pool = (max(candidates,
                    key=lambda idx: max(_rank_value(S[i]) for i in idx))
                if candidates else [])
    if len(pool) < 2:
        return []
    order = sorted(pool, key=lambda i: tuple(-v for v in _rank_value(S[i])))[:2]
    a, b = order
    ta, tb = S[a]["by_task"], S[b]["by_task"]
    # Include every task from both runs; tasks only in one run show as "–"
    all_tasks = sorted(set(ta) | set(tb))
    rows = []
    for t in all_tasks:
        x = ta.get(t)
        y = tb.get(t)
        if x is None:
            rows.append((t, None, y, labels[b]))
        elif y is None:
            rows.append((t, x, None, labels[a]))
        elif x != y:
            rows.append((t, x, y, labels[a] if x > y else labels[b]))
    if not rows:
        return []
    out = [f"## Where they disagree — {labels[a]} vs {labels[b]}\n"]
    out.append(f"| Task | {labels[a]} | {labels[b]} | Winner |\n|---|---|---|---|")
    for t, x, y, winner in rows:
        if x is None:
            out.append(f"| `{t}` | – | {y*100:.0f} % | {winner} (not run) |")
        elif y is None:
            out.append(f"| `{t}` | {x*100:.0f} % | – | {winner} (not run) |")
        else:
            out.append(f"| `{t}` | {x*100:.0f} % | {y*100:.0f} % | {winner} |")
    out.append("")
    return out


def _caveats_section(cfg0, samples, samples_same, agentic):
    out = ["## Caveats\n"]
    ci = ("Every solve rate carries a 95% Wilson interval over the generations behind "
          "it, and a margin between two runs is only a result when the 95% Newcombe "
          "interval of the difference excludes zero. The intervals treat each "
          "generation as independent; samples of one task are correlated, so with few "
          "tasks the true uncertainty is if anything wider. Raise `--samples` before "
          "calling a close race.")
    if samples_same:
        out.append(f"- {cfg0.get('samples')} samples per task. {ci}")
    else:
        out.append(f"- Samples per task differ between runs ({samples}); the runs with "
                   f"fewer samples have wider intervals. {ci}")
    if agentic:
        out.append("- Multi-turn agentic tool use against a sandboxed workspace. One-shot code "
                   "generation is not exercised here.")
    else:
        out.append("- Single-turn Python code generation only. Multi-turn agentic tool use is "
                   "not exercised here.")
    if agentic:
        out.append("- Success is decided by a predicate over the final workspace, never by what "
                   "the model claims. Every task's oracle is verified to solve it first.")
        out.append("- A task abandoned at the turn limit counts as failed; raise `--max-turns` "
                   "before concluding the model cannot do it.")
    else:
        out.append("- A truncated generation counts as a failure; a high `Truncated` column means "
                   "runaway reasoning, which hangs real agents.")
    return out


def _raw_data_section(runs, labels):
    out = ["\n## Raw data\n"]
    for r, line in zip(runs, labels):
        members = r.get("_members")
        if members:
            per = ", ".join(f"{v * 100:.1f}" for v in r["_member_scores"])
            files = ", ".join(f"`{m}`" for m in members)
            metric = "agent score" if r["_member_metric"] == "agent_score" else "pass@1"
            out.append(f"- {files} — {line} (pooled: {len(members)} re-runs as "
                       f"samples of one run; {metric} per re-run {per})")
        else:
            out.append(f"- `{r['_path']}` — {line}")
    out.append("")
    return out


def _grouping_notes(ungrouped):
    """Caveat lines for labels that repeat but could not be pooled."""
    if not ungrouped:
        return []
    names = ", ".join(f"`{label}`" for label in ungrouped)
    return [f"- {names}: several files share this label but predate `suite_hash` "
            "(schema_version 0), so they cannot be proven to have run the same tasks "
            "and are reported as separate runs, not pooled."]


def build(runs, title, question=None, verdict=None, notes=None, short_labels=None,
          setups=False, advice=False, group=True):
    """runs: list of loaded result dicts. Returns Markdown source.

    With *group* (the default), re-runs of one label with the same
    ``suite_hash`` are pooled into one row (see `group_runs`). A caller passing
    *short_labels* sized to its own rows gets them ungrouped.
    """
    ungrouped = []
    runs = [with_cost(r) for r in runs]
    if group and short_labels is None:
        ungrouped = unhashed_label_collisions(runs)
        runs = [pool(g) for g in group_runs(runs)]
    labels = [_label(r) for r in runs]
    short = short_labels or (_setup_short(runs) if setups
                             else [_short(r, line) for r, line in zip(runs, labels)])
    S = [r["summary"] for r in runs]

    out = [f"# {title}\n"]
    if question:
        out.append(f"**Question.** {question}\n")
    if verdict:
        out.append(f"**Verdict.** {verdict}\n")
    cfg0 = S[0]["config"]

    setup_lines, samples, samples_same = _setup_section(S, short)
    out.extend(setup_lines)

    out.extend(_headline_section(
        S, labels, all(s.get("kind") == "agentic" for s in S)))

    result_lines, agentic, _ = _results_section(runs, S, labels, setups)
    out.extend(result_lines)

    out.extend(_cost_section(S, labels))
    out.extend(_charts_section(S, short, agentic))
    out.extend(_difficulty_section(S, labels))
    out.extend(_disagreement_section(runs, S, labels, setups))

    if notes:
        out.append("## Reading the numbers\n")
        out.append(notes.strip() + "\n")

    if advice:
        # `bench setup run` stamps this on its report (issue #76): actionable
        # suggestions derived from each run's own numbers.
        for r in runs:
            from . import advice as advice_mod
            out.extend(advice_mod.section(r["summary"],
                                          title="Suggestions — " + _label(r)))

    out.extend(_caveats_section(cfg0, samples, samples_same, agentic))
    out.extend(_grouping_notes(ungrouped))
    out.extend(_raw_data_section(runs, labels))
    return "\n".join(out)
