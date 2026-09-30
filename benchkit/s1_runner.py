"""System One runner: decision questions scored by exact match, not execution.

Where `runner` extracts code and runs hidden tests, this runner measures a
*decision endpoint*: each generation answers one typed question over a state,
and `passed` is a normalised exact match against the question's `answer`. A
bare option letter counts the same as the full option text, because that is
what the decision models' chat shims (Laya, Bespoke-Nimble, ...) emit.
Verbosity, explanations and empty replies all fail — a model that deliberates
instead of deciding is exactly the failure mode this suite exists to catch.

The summary is the shared `runner.summarize`, so accuracy arrives as the
familiar solve_rate/pass_at_1 with its Wilson interval, and speed as the
per-question tokens, tok/s, TTFT and wall-clock the report already renders.
"""
import concurrent.futures as cf
import re
import time

from . import runner
from .fingerprint import stamp

SYSTEM = (
    "You are a System One decision engine. Read the state, then answer the "
    "question with exactly one of the listed options. Reply with the option "
    "letter or its exact text and nothing else — no reasoning, no explanation."
)

_WS = re.compile(r"\s+")


def _norm(s):
    """Case-, whitespace- and punctuation-insensitive form of one answer."""
    s = _WS.sub(" ", (s or "").strip().lower())
    return s.strip(" \t\"'`*.:;!,?()[]{}<>|")


def _accepted(question):
    """Normalised strings that count as correct for one question.

    The full answer text always counts. When the answer is a listed option,
    its letter forms ("a", "a) <text>", "a. <text>", "a <text>") count too —
    that is the whole surface the decision models' shims produce. Anything
    else, including a different letter or the right text under the wrong
    letter, fails.
    """
    answer = _norm(question["answer"])
    ok = {answer}
    for i, o in enumerate(question.get("options") or []):
        if _norm(o) == answer and i < 26:
            letter = chr(ord("a") + i)
            ok.update((letter, f"{letter}) {answer}", f"{letter}. {answer}",
                       f"{letter} {answer}"))
    return ok


def _score(question, text):
    """(passed, given) — `given` is the normalised reply, None when empty."""
    given = _norm(text)
    return given in _accepted(question), (given or None)


def _render(task, question):
    """The user prompt for one typed question over the task's state."""
    lines = ["State:", task["state"].strip(), "",
             f"Question: {question['question'].strip()}"]
    options = question.get("options") or []
    if options:
        lines.append("Options:")
        lines.extend(f"{chr(ord('A') + i)}) {o}" for i, o in enumerate(options))
        lines.append("Answer with the option letter or its exact text, "
                     "and nothing else.")
    else:
        lines.append("Answer as briefly as possible — a few words at most, "
                     "and nothing else.")
    return "\n".join(lines)


def _items(tasks):
    """Flatten every task's questions into one scored unit each."""
    items = []
    for t in tasks:
        for i, q in enumerate(t["questions"]):
            items.append(dict(q, id=f"{t['id']}/q{i+1}",
                              difficulty=t["difficulty"],
                              prompt=_render(t, q)))
    return items


def run(tasks, cfg, on_result=None, keep_code=False):
    """Run every question of every task `cfg.samples` times.

    Returns (summary, results) — the same contract as `runner.run`, so the
    report's accuracy axis, cost tables and charts work unchanged. With
    `keep_code` each raw reply is stored under `response`.
    """
    client = runner._client(cfg)
    questions = _items(tasks)

    def work(item):
        q, i = item
        try:
            gen = runner.generate(client, cfg, q, i, system=SYSTEM)
        except Exception as e:  # noqa: BLE001 — a dead backend must not kill the suite
            r = dict(task=q["id"], difficulty=q["difficulty"], sample=i,
                     passed=False, error=f"generation failed: {e}", tok_s=None,
                     ttft=None, elapsed=None, completion_tokens=None)
            if on_result:
                on_result(r)
            return r
        text = gen.pop("text")
        ok, given = _score(q, text)
        gen.update(passed=ok, given=given,
                   error="" if ok else f"expected {q['answer']!r}")
        if keep_code:
            gen["response"] = text
        if on_result:
            on_result(gen)
        return gen

    work_items = [(q, i) for q in questions for i in range(cfg.samples)]
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=cfg.concurrency) as ex:
        results = list(ex.map(work, work_items))
    wall = time.perf_counter() - t0
    return stamp(summarize(results, cfg, wall, len(questions)), tasks), results


def summarize(results, cfg, wall, n_questions):
    """The shared summary, stamped `kind: s1` so reports can say 'accuracy'."""
    summary = runner.summarize(results, cfg, wall, n_questions)
    summary["kind"] = "s1"
    return summary


def _lint(task):
    """Data problems in one s1 task; an empty list means clean."""
    if not isinstance(task, dict):
        return ["task entry must be a mapping"]
    problems = []
    if not isinstance(task.get("id"), str) or not task["id"].strip():
        problems.append("id must be a non-empty string")
    if task.get("difficulty") not in ("easy", "medium", "hard"):
        problems.append("difficulty must be easy, medium or hard")
    if not isinstance(task.get("state"), str) or not task["state"].strip():
        problems.append("state must be a non-empty string")
    questions = task.get("questions")
    if not isinstance(questions, list) or not questions:
        problems.append("questions must be a non-empty list")
        return problems
    for i, q in enumerate(questions):
        at = f"questions[{i}]"
        if not isinstance(q, dict):
            problems.append(f"{at}: question entry must be a mapping")
            continue
        if not isinstance(q.get("question"), str) or not q["question"].strip():
            problems.append(f"{at}: question must be a non-empty string")
        if not isinstance(q.get("answer"), str) or not q["answer"].strip():
            problems.append(f"{at}: answer must be a non-empty string")
            continue
        options = q.get("options")
        if options is None:
            continue  # open short-answer question
        if (not isinstance(options, list) or not options
                or not all(isinstance(o, str) and o.strip() for o in options)):
            problems.append(f"{at}: options must be a non-empty list of strings")
            continue
        normed = [_norm(o) for o in options]
        if len(set(normed)) != len(normed):
            problems.append(f"{at}: duplicate options after normalisation")
        if _norm(q.get("answer") or "") not in set(normed):
            problems.append(f"{at}: answer {q.get('answer')!r} is not one "
                            "of the options")
    return problems


def validate(tasks):
    """Lint every task's data. Returns the number of malformed tasks.

    A decision task has no executable reference to prove — its only contract
    is well-formed data: a readable state, typed questions whose answer is
    one of their own options, and task ids unique enough to key a report.
    That is what `bench validate` checks here.
    """
    bad = 0
    counts = {}
    for t in tasks:
        if isinstance(t, dict):
            tid = t.get("id")
            counts[tid] = counts.get(tid, 0) + 1
    for t in tasks:
        problems = _lint(t)
        tid = t.get("id") if isinstance(t, dict) else None
        if counts.get(tid, 0) > 1:
            problems.append(f"duplicate id {tid!r}")
        print(f"  {'ok  ' if not problems else 'FAIL'} {tid}")
        for p in problems:
            print(f"         {p}")
        bad += bool(problems)
    print(f"\n{len(tasks) - bad}/{len(tasks)} tasks pass data lint")
    return bad
