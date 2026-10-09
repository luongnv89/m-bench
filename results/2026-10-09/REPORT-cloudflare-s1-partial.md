# Cloudflare Clef candidates vs S1 incumbent (partial)

**Question.** Should Clef or Clef-Flash replace the current System One incumbent?

**Verdict.** Do not replace the incumbent on this partial evidence. Clef-Flash is viable at 98.0% and matches the historical Jev score, but its margin over today’s Kev-4B result is within uncertainty; full Clef is unmeasured because it needs a shared endpoint stop. Keep the current setup until Clef is measured with approval.

## Setup

| | |
|---|---|
| Endpoint | mixed — `http://localhost:8123` (jev-latest OFF), `http://localhost:8123` (kev-latest OFF), `http://127.0.0.1:8124` (clef-flash OFF) |
| Tasks | 49 |
| Samples per task | 2 (⇒ 98 generations per run) |
| Concurrency | 4 |
| Metric | accuracy over exact-match answers on typed decision questions, with a 95% Wilson interval |

## Headline

| Run | Accuracy (95% CI) | Tokens per task | Time per task |
|---|---|---|---|---|
| typesafe jev-1.13 s1 | 98.0 % (93–99) | 327 in / 38 out | 0.3 s |
| incumbent kev-4b s1 2026-10-09 | 95.9 % (90–98) | 52 in / 61 out | 0.2 s |
| clef-flash-9b s1 warmed 2026-10-09 | 98.0 % (93–99) | 160 in / 0 out | 0.7 s |

<sub>The bracket is the 95% Wilson interval of the solve rate, in points. *Tokens* and *time* are the mean per task attempt (input and output tokens as the endpoint or harness reported them; wall-clock seconds).</sub>

## At a glance

| # | Run | Harness · thinking | Accuracy | Tokens / task | Time / task |
|---|---|---|---|---|---|
| 1 | typesafe jev-1.13 s1 | built-in loop · OFF | `█████████▊` 98 % <sub>(93–99)</sub> | `██████████` 365 | `███▉░░░░░░` 0 s |
| 2 | clef-flash-9b s1 warmed 2026-10-09 | built-in loop · OFF | `█████████▊` 98 % <sub>(93–99)</sub> | `████▍░░░░░` 160 | `██████████` 1 s |
| 3 | incumbent kev-4b s1 2026-10-09 | built-in loop · OFF | `█████████▋` 96 % <sub>(90–98)</sub> | `███▏░░░░░░` 113 | `███▌░░░░░░` 0 s |

<sub>Solve-rate bars run 0–100 %, bracket = 95% interval. Token and time bars are scaled to the costliest row — shorter is cheaper.</sub>

```mermaid
quadrantChart
    title Accuracy vs tokens per task
    x-axis Cheaper --> Costlier - max 365 tok
    y-axis Lower accuracy --> Higher accuracy
    1: [0.96, 0.96]
    2: [0.44, 0.96]
    3: [0.31, 0.96]
```

```mermaid
quadrantChart
    title Accuracy vs time per task
    x-axis Cheaper --> Costlier - max 1 s
    y-axis Lower accuracy --> Higher accuracy
    1: [0.39, 0.96]
    2: [0.96, 0.96]
    3: [0.35, 0.96]
```

<sub>Points are the `#` column above. Up is better, left is cheaper: the top-left corner is the most solved for the least spent. Cost is scaled to the costliest run.</sub>

## Results

| Run | Accuracy | easy | medium | hard | Wall | Mean out tok | Truncated | tok/s |
|---|---|---|---|---|---|---|---|---|
| **typesafe jev-1.13 s1** | **98.0 %** | 100.0 % | 100.0 % | 88.9 % | 7 s | 38 | 0 | 150.8 |
| incumbent kev-4b s1 2026-10-09 | 95.9 % | 95.5 % | 100.0 % | 88.9 % | 6 s | 61 | 0 | 300.8 |
| clef-flash-9b s1 warmed 2026-10-09 | 98.0 % | 100.0 % | 100.0 % | 88.9 % | 17 s | — | 0 | — |

```mermaid
xychart-beta
    title "Accuracy (%)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "clef-flash OFF"]
    y-axis "accuracy %" 0 --> 100
    bar [97.96, 95.92, 97.96]
```

```mermaid
xychart-beta
    title "Cost of that accuracy — suite wall-clock (s)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "clef-flash OFF"]
    y-axis "seconds" 0 --> 19.64
    bar [6.683, 6.033, 17.08]
```

```mermaid
xychart-beta
    title "Cost of that accuracy — tokens per task (in + out)"
    x-axis ["jev-latest OFF", "kev-latest OFF", "clef-flash OFF"]
    y-axis "tokens" 0 --> 419.6
    bar [364.9, 113.3, 160.5]
```

```mermaid
xychart-beta
    title "Mean output tokens per answer"
    x-axis ["jev-latest OFF", "kev-latest OFF", "clef-flash OFF"]
    y-axis "tokens" 0 --> 70.41
    bar [37.59, 61.22, 0]
```

## By difficulty

| Run | easy | medium | hard |
|---|---|---|---|
| typesafe jev-1.13 s1 | `████████` 100 % | `████████` 100 % | `███████▏` 89 % |
| incumbent kev-4b s1 2026-10-09 | `███████▋` 95 % | `████████` 100 % | `███████▏` 89 % |
| clef-flash-9b s1 warmed 2026-10-09 | `████████` 100 % | `████████` 100 % | `███████▏` 89 % |

## Task by task

<sub>Per-task solve rate (%). Tasks the runs disagree on are listed first, widest gap on top.</sub>

| Task | jev-latest OFF | kev-latest OFF | clef-flash OFF |
|---|---|---|---|
| `spam_email/q2` | 🟩 100 | 🟥 0 | 🟩 100 |

- 🟩 **every run solved** (47): `bag_allowance/q1`, `bag_allowance/q2`, `borderline_comment/q1`, `borderline_comment/q2`, `budget_veto/q1`, `budget_veto/q2`, `cafe_hours/q1`, `cafe_hours/q2`, `cafe_hours/q3`, `capital_japan/q1`, `capital_japan/q2`, `chat_resolved/q1`, `chat_resolved/q2`, `device_policy/q1`, `device_policy/q2`, `error_log/q2`, `error_log/q3`, `fruit_basket/q1`, `fruit_basket/q2`, `glowing_review/q1`, `glowing_review/q2`, `golden_retriever/q1`, `golden_retriever/q2`, `harsh_review/q1`, `harsh_review/q2`, `height_order/q1`, `height_order/q2`, `json_order/q1`, `json_order/q2`, `language_french/q1`, `language_french/q2`, `museum_hours/q1`, `museum_hours/q2`, `product_spec/q1`, `product_spec/q2`, `ref_code/q1`, `ref_code/q2`, `refund_eligible/q1`, `refund_eligible/q2`, `sale_item_refund/q1`, `sale_item_refund/q2`, `sale_item_refund/q3`, `spam_email/q1`, `threat_comment/q1`, `threat_comment/q2`, `ticket_billing/q1`, `ticket_billing/q2`
- 🟥 **every run failed** (1): `error_log/q1`

## Cost per task

<sub>Mean per attempt: input / output tokens, then wall-clock seconds. *not reported* = no usage reported for that task; *–* = the run has no cost record for it.</sub>

| Task | typesafe jev-1.13 s1 | incumbent kev-4b s1 2026-10-09 | clef-flash-9b s1 warmed 2026-10-09 |
|---|---|---|---|
| `bag_allowance/q1` | 316 / 31 · 0.3 s | 43 / 52 · 0.2 s | 145 / 0 · 0.7 s |
| `bag_allowance/q2` | 320 / 31 · 0.2 s | 47 / 52 · 0.3 s | 149 / 0 · 0.6 s |
| `borderline_comment/q1` | 309 / 31 · 0.2 s | 36 / 52 · 0.2 s | 138 / 0 · 0.8 s |
| `borderline_comment/q2` | 308 / 31 · 0.3 s | 35 / 52 · 0.1 s | 137 / 0 · 0.5 s |
| `budget_veto/q1` | 313 / 31 · 0.5 s | 40 / 52 · 0.2 s | 142 / 0 · 0.8 s |
| `budget_veto/q2` | 314 / 31 · 0.3 s | 41 / 52 · 0.1 s | 143 / 0 · 0.8 s |
| `cafe_hours/q1` | 328 / 31 · 0.4 s | 55 / 52 · 0.3 s | 157 / 0 · 0.7 s |
| `cafe_hours/q2` | 330 / 31 · 0.2 s | 57 / 52 · 0.2 s | 159 / 0 · 0.7 s |
| `cafe_hours/q3` | 335 / 31 · 0.2 s | 62 / 52 · 0.2 s | 164 / 0 · 0.7 s |
| `capital_japan/q1` | 316 / 50 · 0.3 s | 35 / 79 · 0.2 s | 155 / 0 · 0.6 s |
| `capital_japan/q2` | 315 / 47 · 0.2 s | 35 / 77 · 0.2 s | 155 / 0 · 0.6 s |
| `chat_resolved/q1` | 345 / 51 · 0.3 s | 67 / 80 · 0.2 s | 187 / 0 · 0.7 s |
| `chat_resolved/q2` | 329 / 31 · 0.2 s | 57 / 52 · 0.3 s | 159 / 0 · 0.7 s |
| `device_policy/q1` | 317 / 31 · 0.2 s | 44 / 52 · 0.2 s | 146 / 0 · 0.8 s |
| `device_policy/q2` | 318 / 31 · 0.4 s | 45 / 52 · 0.2 s | 147 / 0 · 0.7 s |
| `error_log/q1` | 333 / 39 · 0.2 s | 58 / 64 · 0.2 s | 169 / 0 · 1.0 s |
| `error_log/q2` | 332 / 38 · 0.2 s | 57 / 63 · 0.2 s | 168 / 0 · 0.7 s |
| `error_log/q3` | 327 / 31 · 0.3 s | 55 / 52 · 0.3 s | 157 / 0 · 0.7 s |
| `fruit_basket/q1` | 315 / 45 · 0.2 s | 36 / 74 · 0.2 s | 156 / 0 · 0.6 s |
| `fruit_basket/q2` | 316 / 45 · 0.3 s | 37 / 74 · 0.2 s | 157 / 0 · 0.8 s |
| `glowing_review/q1` | 316 / 38 · 0.2 s | 40 / 63 · 0.2 s | 151 / 0 · 0.8 s |
| `glowing_review/q2` | 312 / 31 · 0.2 s | 39 / 52 · 0.2 s | 141 / 0 · 0.5 s |
| `golden_retriever/q1` | 316 / 45 · 0.2 s | 36 / 74 · 0.2 s | 156 / 0 · 0.6 s |
| `golden_retriever/q2` | 303 / 31 · 0.3 s | 29 / 52 · 0.2 s | 131 / 0 · 0.7 s |
| `harsh_review/q1` | 342 / 52 · 0.2 s | 58 / 85 · 0.2 s | 187 / 0 · 0.8 s |
| `harsh_review/q2` | 314 / 31 · 0.4 s | 39 / 52 · 0.2 s | 141 / 0 · 0.7 s |
| `height_order/q1` | 305 / 38 · 0.2 s | 29 / 63 · 0.2 s | 140 / 0 · 0.6 s |
| `height_order/q2` | 305 / 38 · 0.2 s | 29 / 62 · 0.1 s | 140 / 0 · 0.7 s |
| `json_order/q1` | 342 / 50 · 0.2 s | 62 / 77 · 0.3 s | 182 / 0 · 0.6 s |
| `json_order/q2` | 343 / 45 · 0.2 s | 65 / 74 · 0.2 s | 185 / 0 · 0.7 s |
| `language_french/q1` | 317 / 45 · 0.2 s | 38 / 74 · 0.3 s | 158 / 0 · 0.9 s |
| `language_french/q2` | 304 / 31 · 0.3 s | 31 / 52 · 0.2 s | 133 / 0 · 0.7 s |
| `museum_hours/q1` | 319 / 31 · 0.3 s | 46 / 51 · 0.2 s | 148 / 0 · 0.8 s |
| `museum_hours/q2` | 326 / 31 · 0.2 s | 53 / 52 · 0.2 s | 155 / 0 · 0.6 s |
| `product_spec/q1` | 315 / 31 · 0.2 s | 40 / 52 · 0.3 s | 142 / 0 · 0.5 s |
| `product_spec/q2` | 314 / 31 · 0.2 s | 39 / 52 · 0.2 s | 141 / 0 · 0.5 s |
| `ref_code/q1` | 355 / 80 · 0.2 s | 71 / 115 · 0.3 s | 209 / 0 · 0.7 s |
| `ref_code/q2` | 349 / 74 · 0.2 s | 74 / 99 · 0.2 s | 185 / 0 · 0.7 s |
| `refund_eligible/q1` | 342 / 31 · 0.2 s | 69 / 49 · 0.2 s | 171 / 0 · 0.6 s |
| `refund_eligible/q2` | 351 / 46 · 0.3 s | 72 / 74 · 0.2 s | 192 / 0 · 0.7 s |
| `sale_item_refund/q1` | 373 / 31 · 0.3 s | 101 / 52 · 0.2 s | 203 / 0 · 0.7 s |
| `sale_item_refund/q2` | 373 / 31 · 0.2 s | 101 / 52 · 0.2 s | 203 / 0 · 0.8 s |
| `sale_item_refund/q3` | 373 / 31 · 0.3 s | 101 / 52 · 0.2 s | 203 / 0 · 0.8 s |
| `spam_email/q1` | 357 / 31 · 0.4 s | 83 / 52 · 0.9 s | 185 / 0 · 0.9 s |
| `spam_email/q2` | 358 / 31 · 0.4 s | 84 / 51 · 0.8 s | 186 / 0 · 0.9 s |
| `threat_comment/q1` | 307 / 31 · 0.2 s | 34 / 52 · 0.3 s | 136 / 0 · 0.6 s |
| `threat_comment/q2` | 308 / 31 · 0.2 s | 35 / 52 · 0.3 s | 137 / 0 · 0.7 s |
| `ticket_billing/q1` | 335 / 46 · 0.2 s | 57 / 74 · 0.2 s | 177 / 0 · 0.6 s |
| `ticket_billing/q2` | 326 / 31 · 0.2 s | 54 / 52 · 0.2 s | 156 / 0 · 0.5 s |

## Reading the numbers

## Scope and run selection

This partial System One comparison covers the current S1 incumbent (Kev-4B), the historical TypeSafe Jev baseline, and a fresh Cloudflare/clef-flash run. All use the same 49-question suite (`suite_hash` `79ff3d7d9b04330f6bae5fa8a723f8dbc93f0c229cb7a49b7df10ecf5fdb9fd0`) with two samples per question. The selected Clef-Flash run used the standard S1 gateway on temporary port 8124, bf16/CUDA, concurrency 4, and completed all 98 generations without transport errors.

The first Clef-Flash attempt (`clef-flash-9b-s1-2026-10-09.json`) had three initial 502s (`lazy wrapper should be called at most once`) during concurrent first-use initialization. After one sequential native request warmed the model, the repeat run completed with zero generation errors and reproduced the 98.0% score. The first raw result is preserved but excluded from the accuracy comparison as an initialization/harness failure, not model evidence.

## Serving constraints

The local Clef-Flash checkpoint is 17.75 GiB of safetensors and ran alongside the existing services. The cached release is commit `17f0b0ad64efb65d273590632833508766b2aae6`; comparison of all cached artifact hashes with Hugging Face's current `fde727a287004204b7518dcc983fe64379776712` found only `README.md` differs. The custom model source was inspected before import; it defines the model and loads safetensors, with no shell execution or dynamic code evaluation observed.

Cloudflare/clef is a 27B bf16 release with 51.19 GiB of weights (expected 55–65 GiB resident). With the active Qwen vLLM endpoint and Kev service, the box had about 40 GiB available after the Clef-Flash process exited, so the full Clef model was not loaded. Prior local notes report that it cannot coexist with the active vLLM endpoint. Measuring it requires taking the shared `vllm-qwen` service / `:8001` endpoint down temporarily; this was not authorized, so Clef remains unmeasured in this campaign.

The temporary `:8124` gateway was stopped after the run. The shared `:8001` and `:8123` endpoints remained responsive.

## Caveats

- 2 samples per task. Every solve rate carries a 95% Wilson interval over the generations behind it, and a margin between two runs is only a result when the 95% Newcombe interval of the difference excludes zero. The intervals treat each generation as independent; samples of one task are correlated, so with few tasks the true uncertainty is if anything wider. Raise `--samples` before calling a close race.
- Single-turn decision questions over a state, scored by exact match against each question's answer key. Code generation and multi-turn tool use are not exercised here.
- Verbose, reasoned or empty replies count as failures — deliberating instead of deciding is the failure mode this suite measures.
- A truncated generation counts as a failure; a high `Truncated` column means runaway reasoning, which hangs real agents.

## Raw data

- `typesafe-jev-1-13-s1.json` — typesafe jev-1.13 s1
- `incumbent-kev-4b-s1-2026-10-09.json` — incumbent kev-4b s1 2026-10-09
- `clef-flash-9b-s1-warmed-2026-10-09.json` — clef-flash-9b s1 warmed 2026-10-09
