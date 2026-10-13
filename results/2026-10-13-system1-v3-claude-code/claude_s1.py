#!/usr/bin/env python3
"""Run the system1 suite through the Claude Code CLI instead of an HTTP endpoint.

Same measurement as s1_runner and ../2026-10-10-system1-v3-200/pi_s1.py —
rendered prompt, s1 SYSTEM preamble (via --system-prompt), exact-match scoring,
shared summarize() — but each generation is an isolated `claude -p` call: no
tools, no MCP, no skills, no hooks, no settings files, no CLAUDE.md, no
auto-memory, no session persistence, run in an empty temp dir. --effort takes
Claude Code's levels (low/medium/high/xhigh/max).

Not removable without --bare (which needs ANTHROPIC_API_KEY; this run uses
OAuth): Claude Code's built-in preamble — an Agent SDK identity line, an env
block (cwd, platform, date) and the account e-mail line. None of it bears on
the decision task.

Usage: claude_s1.py <model-id> <effort> <out.json> [--samples N] [--suite S]
"""
import json
import os
import subprocess
import sys
import tempfile
import time

REPO = os.path.expanduser("~/workspace/luongnv89/m-bench")
sys.path.insert(0, REPO)

from benchkit import runner, s1_runner  # noqa: E402
from benchkit.harness.claudecode import _SCRUB  # noqa: E402
from benchkit.suites import get  # noqa: E402

MODEL, LEVEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SAMPLES = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 1
SUITE = sys.argv[sys.argv.index("--suite") + 1] if "--suite" in sys.argv else "system1-v3"

# a parent Claude Code session's env would make the child a nested run
SCRUB = set(_SCRUB) | {"CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_MESSAGING_SOCKET",
                       "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED",
                       "CLAUDE_PID", "CLAUDE_EFFORT", "AI_AGENT", "CLAUDE_CODE_EXECPATH"}
ENV = {k: v for k, v in os.environ.items() if k not in SCRUB}
ENV.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")

tasks = get(SUITE)
items = s1_runner._items(tasks)

cfg = runner.Config(
    base_url="(claude cli)", model=f"anthropic/{MODEL}", thinking=True,
    max_tokens=128000, samples=SAMPLES, concurrency=1,
    label=f"claude-code-{MODEL}-effort{LEVEL}-{SUITE}",
    harness="claude-code",
    extra={"effort": LEVEL, "transport": "claude -p, isolated (--tools '' "
           "--disable-slash-commands --strict-mcp-config --setting-sources '' "
           "disableAllHooks, no CLAUDE.md/auto-memory, --no-session-persistence)"},
)


def one(item, sample):
    q = item
    argv = ["claude", "-p", q["prompt"], "--model", MODEL, "--effort", LEVEL,
            "--output-format", "json", "--system-prompt", s1_runner.SYSTEM,
            "--tools", "", "--disable-slash-commands", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--no-session-persistence",
            "--setting-sources", "", "--settings", '{"disableAllHooks":true}']
    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="claude-s1-") as wd:
            p = subprocess.run(argv, cwd=wd, env=ENV, capture_output=True,
                               text=True, timeout=900, stdin=subprocess.DEVNULL)
        elapsed = time.perf_counter() - t0
        try:
            d = json.loads(p.stdout)
        except ValueError:
            d = {}
        text = d.get("result") or ""
        if p.returncode != 0 or d.get("is_error") or not text:
            tail = (p.stderr or p.stdout).strip().splitlines()
            return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                        passed=False, given=None, elapsed=elapsed,
                        error="generation failed: " + (tail[-1][:160] if tail
                                                       else f"rc={p.returncode}"),
                        tok_s=None, ttft=None, completion_tokens=None)
        usage = d.get("usage") or {}
        mu = (d.get("modelUsage") or {})
        mid = next(iter(mu), MODEL)
        out_toks = usage.get("output_tokens") or 0  # includes thinking
        think = (usage.get("output_tokens_details") or {}).get("thinking_tokens")
        prompt = sum(usage.get(k) or 0 for k in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        ok, given = s1_runner._score(q, text)
        return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                    passed=ok, given=given,
                    error="" if ok else f"expected {q['answer']!r}",
                    ttft=(d.get("ttft_ms") or 0) / 1000 or None, elapsed=elapsed,
                    prompt_tokens=prompt or None,
                    completion_tokens=out_toks or None,
                    reasoning_tokens=think,
                    cost_usd=d.get("total_cost_usd"),
                    model_reported=mid, reply=text,
                    tok_s=(out_toks / elapsed) if out_toks and elapsed else None)
    except subprocess.TimeoutExpired:
        return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                    passed=False, given=None, elapsed=time.perf_counter() - t0,
                    error="generation failed: claude exceeded 900s",
                    tok_s=None, ttft=None, completion_tokens=None)


results = []
work = [(q, i) for q in items for i in range(SAMPLES)]
t0 = time.perf_counter()
for n, (q, i) in enumerate(work, 1):
    r = one(q, i)
    results.append(r)
    tag = "PASS" if r["passed"] else ("ERR " if "generation failed" in str(r.get("error")) else "FAIL")
    print(f"  {tag}  {q['id']:<18} s{i}  {r.get('completion_tokens') or 0:>5}tok  "
          f"{r.get('elapsed') or 0:>5.1f}s  {r.get('error') or ''}",
          flush=True)
wall = time.perf_counter() - t0

summary = s1_runner.stamp(
    dict(s1_runner.summarize(results, cfg, wall, len(items)),
         **s1_runner.scenario_metrics(results, tasks)), tasks)
with open(OUT, "w") as f:
    json.dump(dict(summary=summary, results=results), f, indent=2)
print(f"\n{summary['pass_at_1'] * 100:.1f}%  "
      f"({sum(1 for r in results if r['passed'])}/{len(results)})  "
      f"wall {wall:.0f}s  -> {OUT}")
