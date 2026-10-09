# NOTES — system1 v2 re-measurement of the v1 model roster (2026-10-09)

Campaign: re-run every model that appeared on the v1 (legacy) landing board on the
new v2 suite — 200 scenarios / 400 questions, `--samples 2`, `--concurrency 1`,
800 scored generations per arm. Jev, Nimble-9B and Kev-4B were already measured in
`../2026-10-09-system1-v2-kev4b-vs-jev/`; this directory covers the rest of the
roster. Shared services untouched: the incumbent router on :8001 and every model
server stayed up; a private gateway on :8124 was used (sequentially) for the
`systemone` and `laya` backends and has been stopped.

## Arms and transport

| Arm | Transport | How it was driven |
|---|---|---|
| Qwen3.6-35B-A3B-NVFP4 think-OFF | direct chat, `http://localhost:8001/v1` model `montimage-dgx-spark` | `bench run --suite system1` |
| Qwen3.6-35B-A3B-NVFP4 think-ON | same endpoint | `+ --thinking --max-tokens 16000` |
| Mercury Decide (`inception/mercury-decide:free`) | private gateway :8124, `S1_BACKEND=systemone`, `S1_DECISION_URL=https://openrouter.ai/api/alpha/decisions`, key from `.env` | typed `choice` per generation; model id reported upstream `inception/mercury-decide-20260930` |
| Laya typed-decisions | private gateway :8124, `S1_BACKEND=laya`, `~/models/laya-typed-decisions` | in-process scorer on CPU, thread executor |

## Results

| Arm | Accuracy (95% CI) | s/q | out-tok/q | Wall | Errors |
|---|---|---|---|---|---|
| Qwen3.6-35B think-ON | **98.6 %** (97.6–99.2) | 9.016 | 766.6 | 7 213 s | 0 |
| Mercury Decide :free | **86.5 %** (84.0–88.7) | 0.490 | 1.0 | 392 s | 0 |
| Qwen3.6-35B think-OFF | **61.8 %** (58.3–65.1) | 0.205 | 3.8 | 164 s | 0 |
| Laya typed-decisions | **33.5 %** (30.3–36.8) | 0.473 | 0 | 378 s | 0 |

Per-family accuracy (80 generations each):

| Family | Qwen-ON | Mercury | Qwen-OFF | Laya |
|---|---:|---:|---:|---:|
| access | 99 | 98 | 76 | 42 |
| dependencies | 99 | 91 | 69 | 18 |
| events | 96 | 95 | 22 | 15 |
| evidence | 98 | 98 | 98 | 68 |
| inventory | 100 | 69 | 56 | 30 |
| money | 100 | 71 | 46 | 32 |
| policy | 100 | 100 | 62 | 30 |
| records | 95 | 81 | 48 | 18 |
| time | 100 | 62 | 61 | 55 |
| triage | 100 | 100 | 79 | 28 |

## What v2 shows that v1 could not

- **Thinking is the biggest single lever on this box**: the same NVFP4 weights go
  61.8 % → 98.6 % when reasoning is enabled. On v1 the gap was 96.9 vs 93.9 —
  v2's longer multi-step states are where reasoning pays. Think-ON is nearly
  saturated (95–100 % in every family; weakest is records at 95 %), at
  9.0 s/question and ~767 reasoning tokens.
- **Mercury Decide :free beats hosted Jev on v2** (86.5 vs 79.5 %, intervals
  disjoint) and is second overall. Its weakest families are time (62 %) and
  inventory/money (~70 %). No 20-req/min throttling appeared this run —
  0.49 s/q end to end.
- **Laya collapses on v2** (73.5 % → 33.5 %): as a non-autoregressive scorer it
  picks among options without reasoning; the harder multi-step families
  (dependencies 18 %, events 15 %, records 18 %) are near chance.
- Mercury and the gateway-typed arms all parse as native `choice`; Qwen-OFF
  often echoes `a) <text>` — the scorer resolves letter-prefixed answers
  correctly (544 such givens, 365 passed).

## Not measurable this session (shared-memory ceiling)

| v1 model | Why it did not run |
|---|---|
| Kev-27B (kev.serve bf16 ~63 GiB) | only ~20 GiB free; would need another shared service stopped |
| Clef-27B (clef bf16 ~55–65 GiB) | v1 required pausing the incumbent vLLM — same constraint |
| Clef-Flash-9B (clef bf16 ~19 GiB) | weights cached, but ~19 GiB into ~20 GiB free risks OOM-killing a shared service |

## Reproduction

```bash
# incumbent, both thinking modes (no gateway)
BENCH_BASE_URL=http://localhost:8001/v1 BENCH_MODEL=montimage-dgx-spark \
  ./bench run --suite system1 --samples 2 --concurrency 1 \
  --label qwen3-6-35b-a3b-nvfp4-thinkoff-system1-v2 --out <this-dir>/…off….json
# think-ON adds: --thinking --max-tokens 16000

# Mercury via private gateway
S1_API_KEY=$OPENROUTER_API_KEY S1_BACKEND=systemone S1_PORT=8124 \
  S1_DECISION_URL=https://openrouter.ai/api/alpha/decisions \
  S1_MODEL=inception/mercury-decide:free python3 configs/s1_gateway.py &
BENCH_BASE_URL=http://localhost:8124/v1 BENCH_MODEL=inception/mercury-decide:free \
  ./bench run --suite system1 --samples 2 --concurrency 1 --label mercury-…

# Laya via private gateway (CPU scorer)
S1_BACKEND=laya S1_PORT=8124 python3 configs/s1_gateway.py &
BENCH_BASE_URL=http://localhost:8124/v1 BENCH_MODEL=laya-typed-decisions \
  ./bench run --suite system1 --samples 2 --concurrency 1 --label laya-…
```

All arms share `suite_hash` 0a6ba6f96eb5585c0e89a14cf655756026ee1413a08afaaee936908d55ef1b7e.
Sibling questions and repeated samples are correlated — intervals describe scored
attempts, not independent cases.
