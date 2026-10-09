#!/usr/bin/env python3
"""Run the system1 suite through the pi CLI instead of an HTTP endpoint.

Same measurement as s1_runner — rendered prompt, s1 SYSTEM preamble, exact-match
scoring, shared summarize() — but each generation is a `pi -p` invocation, so
the arm measures "model through pi" the way `bench harness run` would, without
an agentic loop: --no-tools --no-mcp --no-extensions keep it a pure decision
call. --thinking takes pi's real levels (off/minimal/low/medium/high/xhigh/max),
not the adapter's binary map.

Usage: pi_s1.py <model-id> <thinking-level> <out.json> [--samples N]
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
from benchkit.suites import get  # noqa: E402

MODEL, LEVEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SAMPLES = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 2

tasks = get("system1")
items = s1_runner._items(tasks)

cfg = runner.Config(
    base_url="(pi cli)", model=f"openai/{MODEL}", thinking=LEVEL != "off",
    max_tokens=128000, samples=SAMPLES, concurrency=1,
    label=f"pi-{MODEL}-think{LEVEL}-system1-v2",
    harness="pi",
    extra={"thinking_level": LEVEL, "transport": "pi -p, isolated "
           "(--no-session --no-tools --no-mcp --no-extensions)"},
)


def one(item, sample):
    q = item
    argv = ["pi", "-p", q["prompt"],
            "--provider", "openai", "--model", MODEL,
            "--thinking", LEVEL, "--mode", "json",
            "--system-prompt", s1_runner.SYSTEM,
            "--no-session", "--no-context-files", "--no-extensions",
            "--no-mcp", "--no-tools", "--approve"]
    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="pi-s1-") as wd:
            p = subprocess.run(argv, cwd=wd, capture_output=True, text=True,
                               timeout=900)
        elapsed = time.perf_counter() - t0
        text, usage, mid = "", {}, MODEL
        for line in p.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "message_end":
                m = ev.get("message") or {}
                if m.get("role") == "assistant":
                    mid = m.get("model") or mid
                    usage = m.get("usage") or usage
                    text = "".join(c.get("text", "") for c in m.get("content") or []
                                   if c.get("type") == "text")
        if p.returncode != 0 or not text:
            tail = (p.stderr or p.stdout).strip().splitlines()
            return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                        passed=False, given=None, elapsed=elapsed,
                        error="generation failed: " + (tail[-1][:160] if tail
                                                       else f"rc={p.returncode}"),
                        tok_s=None, ttft=None, completion_tokens=None)
        out_toks = (usage.get("output") or 0) + (usage.get("reasoning") or 0)
        ok, given = s1_runner._score(q, text)
        return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                    passed=ok, given=given,
                    error="" if ok else f"expected {q['answer']!r}",
                    ttft=None, elapsed=elapsed,
                    prompt_tokens=usage.get("input"),
                    completion_tokens=out_toks or None,
                    reasoning_tokens=usage.get("reasoning"),
                    cost_usd=(usage.get("cost") or {}).get("total"),
                    model_reported=mid,
                    tok_s=(out_toks / elapsed) if out_toks and elapsed else None)
    except subprocess.TimeoutExpired:
        return dict(task=q["id"], difficulty=q["difficulty"], sample=sample,
                    passed=False, given=None, elapsed=time.perf_counter() - t0,
                    error="generation failed: pi exceeded 900s",
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
    s1_runner.summarize(results, cfg, wall, len(items)), tasks)
with open(OUT, "w") as f:
    json.dump(dict(summary=summary, results=results), f, indent=2)
print(f"\n{summary['pass_at_1'] * 100:.1f}%  "
      f"({sum(1 for r in results if r['passed'])}/{len(results)})  "
      f"wall {wall:.0f}s  -> {OUT}")
