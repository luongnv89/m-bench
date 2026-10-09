# NOTES — system1 v2 through pi: OpenAI gpt-6-luna / gpt-6.1-sol (2026-10-09)

Campaign: measure two frontier OpenAI models from the user's pi catalogue on
the full v2 suite — 200 scenarios / 400 questions, `--samples 2`, sequential
(concurrency 1), 800 scored generations per arm. The user's exact picks:
**gpt-6-luna at max thinking** and **gpt-6.1-sol at high thinking**.

## Transport — pi, not the s1 gateway

`bench harness run` only accepts agentic suites, so the arm is driven by
`pi_s1.py` (this directory): each rendered s1 question goes through

```
pi -p "<state + question + options>" \
   --provider openai --model <id> --thinking <level> --mode json \
   --system-prompt "<the s1 decision-engine system prompt>" \
   --no-session --no-context-files --no-extensions --no-mcp --no-tools --approve
```

Identical prompt, system preamble and exact-match scorer as every other v2
arm — the only deltas are pi's process boundary and the OpenAI `openai-responses`
API upstream (pi's catalogue credentials). Latency includes ~1 s of pi process
startup per generation; it is reported but not comparable to the gateway arms —
accuracy is the comparable axis. `--no-tools` keeps the arm a pure decision call:
no file or shell access, same output surface as a chat completion.

## Results

| Model · thinking | Accuracy (95% CI) | s/q | out+reasoning tok/q | Wall | Cost (pi-reported) | Errors |
|---|---|---|---|---|---|---|
| **gpt-6.1-sol · high** | **100.0 %** (99.5–100) | 3.921 | 28.9 | 3 137 s | $0.61 | 0 |
| **gpt-6-luna · max** | **99.1 %** (98.2–99.6) | 5.678 | 76.6 | 4 543 s | $0.04 | 0 |

- **v2 is now saturated at the frontier.** gpt-6.1-sol at `high` answers all
  800 generations correctly, including every open `records` question — the
  family that capped the typed-decision backends. Per the runbook's own rule:
  at ~100 % the suite has stopped measuring this tier; a v3 needs harder
  states (longer horizons, ambiguous or conflicting evidence).
- Luna's 7 misses are all in `records`, and 5 of them are the free-text open
  questions — reachable through pi but genuinely hard (expected `NONE`,
  `REF-2-Q`, `conflict`, `missing`). Not a transport artifact.
- **Frontier reasoning ≫ tuned small decision models on v2**: sol/luna ≥ 99 %
  vs Qwen think-ON 98.6 % vs Mercury 86.5 % vs Jev 79.5 %. The gap that matters
  for this workload is reasoning depth, not the decision-typed transport —
  the typed contract exists to make *weak* models answer reliably.

## Cost note

Pi-reported spend: sol $0.61, luna $0.04 for 800 generations each — luna's
`max` is billed cheaper per token than sol's `high` despite its name; the
reported per-call cost fields are in the result JSONs.

## Reproduction

```bash
python3 results/2026-10-09-system1-v2-pi-openai/pi_s1.py gpt-6-luna max \
    results/…/gpt-6-luna-thinkmax-system1-v2.json --samples 2
python3 results/2026-10-09-system1-v2-pi-openai/pi_s1.py gpt-6.1-sol high \
    results/…/gpt-6-1-sol-thinkhigh-system1-v2.json --samples 2
```

Same `suite_hash` as every v2 arm: 0a6ba6f96eb5585c0e89a14cf655756026ee1413a08afaaee936908d55ef1b7e.
