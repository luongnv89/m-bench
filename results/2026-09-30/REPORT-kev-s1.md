# Kev-4B vs Jev baseline on system1

**Question.** Should Kev-4B replace Jev behind the s1 endpoint?

**Verdict.** Statistically tied with Jev on this suite (95.9% vs 98.0%; margin -2.1pp inside the n=98 noise floor) and the fastest local backend measured (0.23s/q vs Jev's 0.27s WAN). Its only net deficit is spam_email/q2 — it fails the same error_log/q1 abstention question Jev fails. A viable drop-in local replacement where an API key or WAN hop is unwanted; Nimble-9B (98.0%, exact tie) remains the safest swap on accuracy evidence alone, while Kev-4B wins on latency and is the only candidate you can fine-tune on your own questions. Footprint: 15 GiB on the GPU alongside the incumbent.

## Setup

| | |
|---|---|
| Endpoint | mixed — `http://localhost:8123` (jev-latest OFF), `http://localhost:8123` (kev-latest OFF), `http://localhost:8123` (nimble OFF), `http://localhost:8001` (montimage-dgx-sp OFF) |
| Tasks | 49 |
| Samples per task | 2 (⇒ 98 generations per run) |
| Concurrency | 4 |
| Metric | accuracy over exact-match answers on typed decision questions, with a 95% Wilson interval |

## Headline

| Run | Accuracy (95% CI) | Tokens per task | Time per task |
|---|---|---|---|---|
| typesafe jev-1.13 s1 | 98.0 % (93–99) | 327 in / 38 out | 0.3 s |
| kev-4b s1 | 95.9 % (90–98) | 52 in / 61 out | 0.2 s |
| bespoke-nimble-9b ollama s1 | 98.0 % (93–99) | 188 in / 1 out | 0.5 s |
| incumbent-qwen3.6-s1-off | 96.9 % (91–99) | 135 in / 4 out | 0.7 s |

<sub>The bracket is the 95% Wilson interval of the solve rate, in points. *Tokens* and *time* are the mean per task attempt (input and output tokens as the endpoint or harness reported them; wall-clock seconds).</sub>

## At a glance

| # | Run | Harness · thinking | Accuracy | Tokens / task | Time / task |
|---|---|---|---|---|---|
| 1 | typesafe jev-1.13 s1 | built-in loop · OFF | `█████████▊` 98 % <sub>(93–99)</sub> | `██████████` 365 | `███▉░░░░░░` 0 s |
| 2 | bespoke-nimble-9b ollama s1 | built-in loop · OFF | `█████████▊` 98 % <sub>(93–99)</sub> | `█████▏░░░░` 189 | `███████▌░░` 1 s |
| 3 | incumbent-qwen3.6-s1-off | built-in loop · OFF | `█████████▊` 97 % <sub>(91–99)</sub> | `███▉░░░░░░` 139 | `██████████` 1 s |
| 4 | kev-4b s1 | built-in loop · OFF | `█████████▋` 96 % <sub>(90–98)</sub> | `███▏░░░░░░` 113 | `███▍░░░░░░` 0 s |

<sub>Solve-rate bars run 0–100 %, bracket = 95% interval. Token and time bars are scaled to the costliest row — shorter is cheaper.</sub>

```mermaid
quadrantChart
    title Accuracy vs tokens per task
    x-axis Cheaper --> Costlier - max 365 tok
    y-axis Lower accuracy --> Higher accuracy
    1: [0.96, 0.96]
    2: [0.52, 0.96]
    3: [0.38, 0.96]
    4: [0.31, 0.96]
```

```mermaid
quadrantChart
    title Accuracy vs time per task
    x-axis Cheaper --> Costlier - max 1 s
    y-axis Lower accuracy --> Higher accuracy
    1: [0.39, 0.96]
    2: [0.75, 0.96]
    3: [0.96, 0.96]
    4: [0.34, 0.96]
```

<sub>Points are the `#` column above. Up is better, left is cheaper: the top-left corner is the most solved for the least spent. Cost is scaled to the costliest run.</sub>

## Results

| Run | Accuracy | easy | medium | hard | Wall | Mean out tok | Truncated | tok/s |
|---|---|---|---|---|---|---|---|---|
| **typesafe jev-1.13 s1** | **98.0 %** | 100.0 % | 100.0 % | 88.9 % | 7 s | 38 | 0 | 150.8 |
| kev-4b s1 | 95.9 % | 95.5 % | 100.0 % | 88.9 % | 6 s | 61 | 0 | 297.9 |
| bespoke-nimble-9b ollama s1 | 98.0 % | 100.0 % | 100.0 % | 88.9 % | 13 s | 1 | 0 | 2.0 |
| incumbent-qwen3.6-s1-off | 96.9 % | 97.7 % | 100.0 % | 88.9 % | 17 s | 4 | 0 | 8.8 |

```mermaid
xychart-beta
    title "Accuracy (%)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "nimble OFF", "montimage-dgx-sp OFF"]
    y-axis "accuracy %" 0 --> 100
    bar [97.96, 95.92, 97.96, 96.94]
```

```mermaid
xychart-beta
    title "Cost of that accuracy — suite wall-clock (s)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "nimble OFF", "montimage-dgx-sp OFF"]
    y-axis "seconds" 0 --> 19.48
    bar [6.683, 5.817, 12.9, 16.94]
```

```mermaid
xychart-beta
    title "Cost of that accuracy — tokens per task (in + out)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "nimble OFF", "montimage-dgx-sp OFF"]
    y-axis "tokens" 0 --> 419.6
    bar [364.9, 113.2, 188.8, 139.3]
```

```mermaid
xychart-beta
    title "Mean output tokens per answer"
    x-axis ["jev-latest OFF", "kev-latest OFF", "nimble OFF", "montimage-dgx-sp OFF"]
    y-axis "tokens" 0 --> 70.36
    bar [37.59, 61.18, 1, 4.102]
```

## By difficulty

| Run | easy | medium | hard |
|---|---|---|---|
| typesafe jev-1.13 s1 | `████████` 100 % | `████████` 100 % | `███████▏` 89 % |
| kev-4b s1 | `███████▋` 95 % | `████████` 100 % | `███████▏` 89 % |
| bespoke-nimble-9b ollama s1 | `████████` 100 % | `████████` 100 % | `███████▏` 89 % |
| incumbent-qwen3.6-s1-off | `███████▉` 98 % | `████████` 100 % | `███████▏` 89 % |

## Task by task

<sub>Per-task solve rate (%). Tasks the runs disagree on are listed first, widest gap on top.</sub>

| Task | jev-latest OFF | kev-latest OFF | nimble OFF | montimage-dgx-sp OFF |
|---|---|---|---|---|
| `spam_email/q2` | 🟩 100 | 🟥 0 | 🟩 100 | 🟩 100 |
| `ref_code/q2` | 🟩 100 | 🟩 100 | 🟩 100 | 🟨 50 |

- 🟩 **every run solved** (46): `bag_allowance/q1`, `bag_allowance/q2`, `borderline_comment/q1`, `borderline_comment/q2`, `budget_veto/q1`, `budget_veto/q2`, `cafe_hours/q1`, `cafe_hours/q2`, `cafe_hours/q3`, `capital_japan/q1`, `capital_japan/q2`, `chat_resolved/q1`, `chat_resolved/q2`, `device_policy/q1`, `device_policy/q2`, `error_log/q2`, `error_log/q3`, `fruit_basket/q1`, `fruit_basket/q2`, `glowing_review/q1`, `glowing_review/q2`, `golden_retriever/q1`, `golden_retriever/q2`, `harsh_review/q1`, `harsh_review/q2`, `height_order/q1`, `height_order/q2`, `json_order/q1`, `json_order/q2`, `language_french/q1`, `language_french/q2`, `museum_hours/q1`, `museum_hours/q2`, `product_spec/q1`, `product_spec/q2`, `ref_code/q1`, `refund_eligible/q1`, `refund_eligible/q2`, `sale_item_refund/q1`, `sale_item_refund/q2`, `sale_item_refund/q3`, `spam_email/q1`, `threat_comment/q1`, `threat_comment/q2`, `ticket_billing/q1`, `ticket_billing/q2`
- 🟥 **every run failed** (1): `error_log/q1`

## Cost per task

<sub>Mean per attempt: input / output tokens, then wall-clock seconds. *not reported* = no usage reported for that task; *–* = the run has no cost record for it.</sub>

| Task | typesafe jev-1.13 s1 | kev-4b s1 | bespoke-nimble-9b ollama s1 | incumbent-qwen3.6-s1-off |
|---|---|---|---|---|
| `bag_allowance/q1` | 316 / 31 · 0.3 s | 43 / 52 · 0.3 s | 171 / 1 · 0.5 s | 126 / 4 · 0.3 s |
| `bag_allowance/q2` | 320 / 31 · 0.2 s | 47 / 52 · 0.3 s | 175 / 1 · 0.5 s | 130 / 4 · 0.4 s |
| `borderline_comment/q1` | 309 / 31 · 0.2 s | 36 / 52 · 0.2 s | 164 / 1 · 0.6 s | 119 / 4 · 0.3 s |
| `borderline_comment/q2` | 308 / 31 · 0.3 s | 35 / 52 · 0.1 s | 163 / 1 · 0.6 s | 118 / 4 · 0.3 s |
| `budget_veto/q1` | 313 / 31 · 0.5 s | 40 / 52 · 0.2 s | 168 / 1 · 0.6 s | 123 / 4 · 0.4 s |
| `budget_veto/q2` | 314 / 31 · 0.3 s | 41 / 52 · 0.2 s | 169 / 1 · 0.6 s | 124 / 4 · 0.3 s |
| `cafe_hours/q1` | 328 / 31 · 0.4 s | 55 / 52 · 0.3 s | 183 / 1 · 0.5 s | 138 / 4 · 0.4 s |
| `cafe_hours/q2` | 330 / 31 · 0.2 s | 57 / 52 · 0.3 s | 185 / 1 · 0.5 s | 140 / 4 · 0.5 s |
| `cafe_hours/q3` | 335 / 31 · 0.2 s | 62 / 52 · 0.2 s | 190 / 1 · 0.5 s | 145 / 4 · 0.3 s |
| `capital_japan/q1` | 316 / 50 · 0.3 s | 35 / 79 · 0.2 s | 184 / 1 · 0.5 s | 116 / 4 · 1.0 s |
| `capital_japan/q2` | 315 / 47 · 0.2 s | 35 / 77 · 0.2 s | 183 / 1 · 0.5 s | 117 / 4 · 0.5 s |
| `chat_resolved/q1` | 345 / 51 · 0.3 s | 67 / 80 · 0.3 s | 219 / 1 · 0.5 s | 151 / 4 · 0.4 s |
| `chat_resolved/q2` | 329 / 31 · 0.2 s | 57 / 52 · 0.4 s | 186 / 1 · 0.5 s | 140 / 4 · 0.4 s |
| `device_policy/q1` | 317 / 31 · 0.2 s | 44 / 52 · 0.2 s | 172 / 1 · 0.6 s | 127 / 4 · 0.5 s |
| `device_policy/q2` | 318 / 31 · 0.4 s | 45 / 52 · 0.2 s | 173 / 1 · 0.5 s | 128 / 4 · 0.5 s |
| `error_log/q1` | 333 / 39 · 0.2 s | 58 / 63 · 0.3 s | 196 / 1 · 0.5 s | 142 / 4 · 0.4 s |
| `error_log/q2` | 332 / 38 · 0.2 s | 57 / 62 · 0.4 s | 194 / 1 · 0.5 s | 144 / 5 · 0.5 s |
| `error_log/q3` | 327 / 31 · 0.3 s | 55 / 52 · 0.3 s | 183 / 1 · 0.5 s | 138 / 4 · 0.4 s |
| `fruit_basket/q1` | 315 / 45 · 0.2 s | 36 / 74 · 0.2 s | 181 / 1 · 0.4 s | 125 / 5 · 0.9 s |
| `fruit_basket/q2` | 316 / 45 · 0.3 s | 37 / 74 · 0.3 s | 182 / 1 · 0.4 s | 126 / 2 · 1.4 s |
| `glowing_review/q1` | 316 / 38 · 0.2 s | 40 / 63 · 0.2 s | 177 / 1 · 0.5 s | 124 / 4 · 1.3 s |
| `glowing_review/q2` | 312 / 31 · 0.2 s | 39 / 52 · 0.2 s | 167 / 1 · 0.5 s | 122 / 4 · 1.5 s |
| `golden_retriever/q1` | 316 / 45 · 0.2 s | 36 / 74 · 0.3 s | 182 / 1 · 0.5 s | 121 / 3 · 0.5 s |
| `golden_retriever/q2` | 303 / 31 · 0.3 s | 29 / 52 · 0.2 s | 157 / 1 · 0.5 s | 112 / 4 · 0.4 s |
| `harsh_review/q1` | 342 / 52 · 0.2 s | 58 / 85 · 0.2 s | 213 / 1 · 0.6 s | 149 / 2 · 0.4 s |
| `harsh_review/q2` | 314 / 31 · 0.4 s | 39 / 52 · 0.2 s | 167 / 1 · 0.6 s | 122 / 4 · 0.5 s |
| `height_order/q1` | 305 / 38 · 0.2 s | 29 / 62 · 0.2 s | 165 / 1 · 0.5 s | 113 / 3 · 0.4 s |
| `height_order/q2` | 305 / 38 · 0.2 s | 29 / 62 · 0.1 s | 165 / 1 · 0.5 s | 113 / 3 · 0.4 s |
| `json_order/q1` | 342 / 50 · 0.2 s | 62 / 77 · 0.2 s | 212 / 1 · 0.6 s | 145 / 4 · 0.5 s |
| `json_order/q2` | 343 / 45 · 0.2 s | 65 / 74 · 0.2 s | 213 / 1 · 0.6 s | 154 / 2 · 0.4 s |
| `language_french/q1` | 317 / 45 · 0.2 s | 38 / 74 · 0.2 s | 184 / 1 · 0.5 s | 123 / 4 · 0.5 s |
| `language_french/q2` | 304 / 31 · 0.3 s | 31 / 52 · 0.2 s | 159 / 1 · 0.5 s | 114 / 4 · 0.5 s |
| `museum_hours/q1` | 319 / 31 · 0.3 s | 46 / 51 · 0.2 s | 174 / 1 · 0.5 s | 129 / 4 · 0.5 s |
| `museum_hours/q2` | 326 / 31 · 0.2 s | 53 / 52 · 0.2 s | 181 / 1 · 0.5 s | 136 / 4 · 0.5 s |
| `product_spec/q1` | 315 / 31 · 0.2 s | 40 / 52 · 0.3 s | 168 / 1 · 0.5 s | 123 / 4 · 0.3 s |
| `product_spec/q2` | 314 / 31 · 0.2 s | 39 / 52 · 0.4 s | 167 / 1 · 0.5 s | 122 / 4 · 0.5 s |
| `ref_code/q1` | 355 / 80 · 0.2 s | 71 / 115 · 0.3 s | 250 / 1 · 0.5 s | 118 / 8 · 0.5 s |
| `ref_code/q2` | 349 / 74 · 0.2 s | 74 / 99 · 0.2 s | 238 / 1 · 0.5 s | 161 / 16 · 0.8 s |
| `refund_eligible/q1` | 342 / 31 · 0.2 s | 69 / 49 · 0.2 s | 198 / 1 · 0.5 s | 152 / 4 · 0.4 s |
| `refund_eligible/q2` | 351 / 46 · 0.3 s | 72 / 74 · 0.2 s | 220 / 1 · 0.6 s | 157 / 2 · 0.4 s |
| `sale_item_refund/q1` | 373 / 31 · 0.3 s | 101 / 52 · 0.3 s | 230 / 1 · 0.7 s | 184 / 4 · 0.4 s |
| `sale_item_refund/q2` | 373 / 31 · 0.2 s | 101 / 50 · 0.2 s | 230 / 1 · 0.7 s | 184 / 4 · 0.4 s |
| `sale_item_refund/q3` | 373 / 31 · 0.3 s | 101 / 52 · 0.1 s | 230 / 1 · 0.5 s | 184 / 4 · 0.4 s |
| `spam_email/q1` | 357 / 31 · 0.4 s | 83 / 52 · 0.3 s | 211 / 1 · 0.5 s | 166 / 4 · 4.9 s |
| `spam_email/q2` | 358 / 31 · 0.4 s | 84 / 52 · 0.4 s | 212 / 1 · 0.5 s | 167 / 4 · 5.0 s |
| `threat_comment/q1` | 307 / 31 · 0.2 s | 34 / 52 · 0.2 s | 162 / 1 · 0.5 s | 117 / 4 · 0.4 s |
| `threat_comment/q2` | 308 / 31 · 0.2 s | 35 / 52 · 0.2 s | 163 / 1 · 0.5 s | 118 / 4 · 0.4 s |
| `ticket_billing/q1` | 335 / 46 · 0.2 s | 57 / 75 · 0.2 s | 204 / 1 · 0.4 s | 142 / 3 · 0.5 s |
| `ticket_billing/q2` | 326 / 31 · 0.2 s | 54 / 52 · 0.2 s | 182 / 1 · 0.4 s | 137 / 4 · 0.4 s |

## Reading the numbers

## Method notes — Kev-4B on system1 (issue #104 follow-up)

Kev-4B (`jaredpalmer/kev-4b`, github.com/jaredpalmer/kev) was measured through
the **same transport** as every s1 candidate: the standard gateway
(`configs/s1_gateway.py`) on `http://localhost:8123/v1`, which parses each
rendered s1 prompt back into `(state, question, options)` and issues one typed
`choice` question per generation. A new `S1_BACKEND=kev` was added for this
run; it reuses `ask_systemone` **verbatim** — kev.serve implements the Jev
`/v1/systemone` contract natively, so only the upstream URL differs from the
`nimble` backend (`KEV_BASE_URL=http://localhost:8009/v1`,
`KEV_MODEL=kev-latest`). No API key.

### Serving

- `uv run python -m kev.serve --run jaredpalmer/kev-4b --port 8009` in a clone
  at `~/workspace/luongnv89/kev` (`uv sync --extra serve`).
- The repo pins `torch>=2.6,<2.9`; PyPI's aarch64 wheel for 2.8.0 is CPU-only,
  so the venv was moved to `torch==2.8.0+cu129` from `download.pytorch.org`.
  That build's kernels target sm_80–sm_120 while the GB10 is sm_121 — ops run
  via PTX JIT fallback (bf16 matmul + SDPA verified). Functional; possibly
  slower than a native sm_121 build.
- Adapter r=16 on frozen Qwen3.5-4B-Base, bf16, CUDA, shipped temperature
  2.41. ~15 GiB measured on the GPU **alongside** the incumbent vLLM service
  (67.6 GiB) and the mon-image app (21.9 GiB) — nothing was restarted.
- Model size choice: 4B because ~23.5 GiB of unified memory was free —
  kev-9b (~19 GiB) is dicey and kev-27b (~51 GiB) does not fit without taking
  the shared endpoint down.

### Measurement

- `./bench run --suite system1 --samples 2` → 98 generations, concurrency 4.
- Result: **95.9 %** (95 % CI 90.0–98.4), 0.23 s/question — vs Jev's 98.0 %
  (CI 92.9–99.4) at 0.27 s/question (hosted WAN latency).
- Failed generations (4/98): `spam_email/q2` twice (answered `yes`, expected
  `no`) and `error_log/q1` twice (`no`, expected `cannot determine`) — the
  same epistemic-abstention question that accounts for **all** of Jev's
  failures. Kev's only net deficit vs Jev is `spam_email/q2`.
- Usage accounting is not line-item comparable: Kev reports ~52 in / 61 out
  tokens per generation (its internal state + option-branch encoding for the
  pointer readout) against Jev's ~327 in / 38 out (rendered-prompt
  accounting). Latency is the comparable cost column — and Kev is local.

### Context vs other candidates

Incumbent Qwen3.6-35B (vLLM, thinking off) scores 96.9 % at 0.69 s/q on the
same suite — Kev-4B, ~9× smaller, is within a point of it and ~3× faster.
Nimble-9B remains the only candidate *tied* to Jev (98.0 %); Kev-4B is one
question lower, inside the noise at n=98. Kev's differentiator is trainable:
its fine-tune loop (skills/kev-finetune) lets you adapt the checkpoint to your
own questions, which Nimble's weights do not offer.

Translation limitations, unchanged from the Jev baseline: open questions fall
back to Choice over deduped state tokens; `noul`/`score` primitives
unexercised; one upstream call per generation.

## Caveats

- 2 samples per task. Every solve rate carries a 95% Wilson interval over the generations behind it, and a margin between two runs is only a result when the 95% Newcombe interval of the difference excludes zero. The intervals treat each generation as independent; samples of one task are correlated, so with few tasks the true uncertainty is if anything wider. Raise `--samples` before calling a close race.
- Single-turn decision questions over a state, scored by exact match against each question's answer key. Code generation and multi-turn tool use are not exercised here.
- Verbose, reasoned or empty replies count as failures — deliberating instead of deciding is the failure mode this suite measures.
- A truncated generation counts as a failure; a high `Truncated` column means runaway reasoning, which hangs real agents.

## Raw data

- `typesafe-jev-1-13-s1.json` — typesafe jev-1.13 s1
- `kev-4b-s1.json` — kev-4b s1
- `bespoke-nimble-9b-ollama-s1.json` — bespoke-nimble-9b ollama s1
- `incumbent-qwen3-6-s1-off.json` — incumbent-qwen3.6-s1-off
