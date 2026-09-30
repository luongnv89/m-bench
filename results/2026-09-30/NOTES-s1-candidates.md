## Method notes — s1 candidate re-runs (issues #102, #104)

All three candidates were measured through the **same transport**: the standard
s1 gateway (`configs/s1_gateway.py`) on `http://localhost:8123/v1`, which parses
each rendered s1 prompt back into `(state, question, options)` and issues one
typed `choice` question per generation. Only `S1_BACKEND` changed between runs —
the benchmark client, suite, samples (2) and concurrency (4) were identical.

| Backend | Upstream | Serving |
|---|---|---|
| `typesafe` | `api.typesafe.ai/v1/systemone` | Hosted TypeSafe API (WAN) |
| `nimble` | Ollama 0.35.0 `localhost:11434/v1/systemone` | `bespokelabs/Bespoke-Nimble-9B`, merged Q8_0 (~9.5 GiB) on GB10 CUDA |
| `laya` | in-process `laya.predict` (thread executor) | `convaiinnovations/laya` `typed-decisions` checkpoint (~843 MB) |

- **Nimble** implements the Jev `/v1/systemone` contract natively in Ollama
  ≥0.35 — the gateway's translator is shared verbatim with the typesafe
  backend. Upstream `usage` (in/out tokens) is reported by Ollama. It answered
  the open extraction question (`ref_code/q1` → `ZX-4821-Q`) correctly via the
  same candidate-token Choice fallback Jev used.
- **Laya** is a non-autoregressive ModernBERT-style scorer; `usage` reports
  input tokens only (0 output by construction). It ran on **CPU** — the GB10's
  free memory was occupied by the incumbent vLLM service, which was not
  restarted (shared endpoint). Vendor estimates ~10–15× faster on GPU
  (~35 ms/question), so its 0.5 s/question is a floor, not a ceiling.
  Its root checkpoint is tuned for guardrails and scored near-chance in smoke
  tests; the **`typed-decisions` checkpoint** is the artifact measured here.
- **Jev** numbers are the earlier baseline run, re-listed for comparison; its
  latency is hosted WAN latency, not local inference.

Translation limitations, unchanged from the Jev baseline: open questions fall
back to Choice over state tokens; `noul`/`score` primitives unexercised
(uniform `choice`); one upstream call per question-generation.

**Verdict:** Nimble is a drop-in Jev replacement for this workload — identical
98.0 % accuracy on the identical transport, fully local, no API key, ~9.5 GiB
quantized. Laya typed-decisions (73.5 %) is not a replacement at this
checkpoint: it fails 12 distinct tasks across all difficulties. Neither margin
vs Jev needs a confidence argument — Nimble is tied to the point and Laya's
deficit (−24.5 pp) far exceeds the noise floor.
