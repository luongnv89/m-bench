# The standard System One endpoint

One stable URL — `http://localhost:8123/v1` — serves every System One decision
workload on this machine. Applications and the `system1` bench suite code
against it once; **which model answers is a deployment detail** chosen by the
gateway's `S1_BACKEND`. Replacing Jev with a better decision model is an env
change and a restart, not an application change.

```
app / bench ──► :8123/v1 (OpenAI chat subset) ──► s1_gateway.py
                                                   │
                  S1_BACKEND ───────────────────────────┤
                  │          │          │         │     │
               typesafe    nimble      laya     kev   proxy
                  │          │          │         │     │
            api.typesafe  ollama    in-process  kev.  S1_UPSTREAM
            /v1/systemone /v1/      predict()   serve (vLLM, llama.cpp,
                          systemone           /v1/    any OpenAI model)
                                              systemone
```

## The contract

Transport: the OpenAI subset the s1 runner uses.

| Endpoint | Notes |
|---|---|
| `GET /v1/models` | backend's model list (proxied verbatim in `proxy` mode) |
| `POST /v1/chat/completions` | `messages`, `stream`, `stream_options.include_usage` honoured; everything else (`chat_template_kwargs`, `max_tokens`, temperature, …) ignored or forwarded |

Semantics — what an application may rely on:

- A request is *one decision question*: the user message carries `State:`, one
  `Question:`, and either an `Options:` block or the open-answer trailer (the
  exact render `benchkit/s1_runner._render` emits).
- The reply is **the decision, and nothing else** — the option letter or its
  exact text, or a few-word short answer. Prose, reasoning, caveats and empty
  replies are contract violations; the suite scores them as failures, which is
  precisely why an app behind this endpoint "works as expected".
- `usage` reports the backend's real tokens when it reports them.

## The baseline: TypeSafe Jev

`S1_BACKEND=typesafe` (the default) serves Jev — the measured reference every
candidate is compared against.

| Metric | Jev `jev-1.13.0` (`jev-latest`) |
|---|---|
| Accuracy on `system1` | **98.0 %** (95 % CI 92.9–99.4, n=98) |
| Time per question | 0.3 s |
| Tokens per question | 327 in / 38 out |
| Failure modes observed | `error_log/q1` (epistemic "cannot determine") only |

Raw run: `results/2026-09-30/typesafe-jev-1-13-s1.json` · comparison:
`results/2026-09-30/REPORT-jev-s1.md` · method notes: `NOTES-jev-s1.md`.

Measured candidates through this same endpoint (issue #104):

| Candidate | Backend | Accuracy | Notes |
|---|---|---|---|
| Bespoke-Nimble-9B (Ollama Q8_0) | `nimble` | **98.0 %** — ties Jev | drop-in replacement; local, no API key |
| Laya `typed-decisions` | `laya` | 73.5 % | not a replacement at this checkpoint; CPU-bound run |
| Kev-4B (`kev.serve`, bf16) | `kev` | 95.9 % — inside noise | local, ~15 GiB measured, fine-tunable; misses only `spam_email/q2` beyond Jev's own `error_log/q1` |
| Kev-27B (`kev.serve`, bf16) | `kev` | **98.0 %** — ties Jev | local, ~63 GiB measured; cannot coexist with the incumbent vLLM endpoint on this box — needed `vllm-qwen.service` stopped to run; only miss is `error_log/q1`, identical to Jev's |

Full comparison: `results/2026-09-30/REPORT-s1-candidates.md` (+ `NOTES-s1-candidates.md`);
Kev runs: `results/2026-09-30/REPORT-kev-s1.md` (+ `NOTES-kev-s1.md`),
`results/2026-10-01/REPORT-kev27b-s1.md` (+ `NOTES-kev27b-s1.md`).

## Backends

### `typesafe` (default) — TypeSafe Jev

```bash
TYPESAFE_API_KEY=... python3 configs/typesafe-jev-shim.py   # or s1_gateway.py
```

Each s1 prompt is parsed back into `(state, question, options)` and issued as
one `choice` call to `api.typesafe.ai/v1/systemone`. Open questions (no options)
become a choice over deduped state tokens — the documented
"select instead of generate" pattern. `usage` maps to OpenAI token fields.

### `proxy` — any OpenAI-native model

```bash
S1_BACKEND=proxy S1_UPSTREAM=http://localhost:8001/v1 python3 configs/s1_gateway.py
```

Forwards requests and streaming responses verbatim. This is how a locally
served candidate — Bespoke-Nimble-9B on vLLM, a GGUF on llama.cpp, an ollama
model — answers behind the same URL Jev uses. Zero translation, zero drift:
the app sees the same wire contract, the model sees the same prompt.

### `nimble` — Bespoke-Nimble-9B via Ollama

```bash
ollama pull nimble            # needs Ollama >= 0.35, ~9.5 GiB Q8_0
S1_BACKEND=nimble python3 configs/s1_gateway.py
```

Ollama ≥ 0.35 exposes `/v1/systemone` for Nimble — the **same Jev contract**
TypeSafe serves — so `ask_systemone` is shared verbatim with the `typesafe`
backend (no API key; `NIMBLE_BASE_URL`, `NIMBLE_MODEL` tune the upstream).
Measured: 98.0 % accuracy, 0.5 s/question, 1 out-token — a proven local Jev
replacement for this workload.

### `kev` — jaredpalmer/kev via kev.serve

```bash
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009
S1_BACKEND=kev python3 configs/s1_gateway.py
```

Kev is a local Jev-style decision model (LoRA adapter on a frozen Qwen3.5
base, prefill-only pointer readout) and `kev.serve` exposes the **same**
`/v1/systemone` contract — `ask_systemone` is shared verbatim with the
`typesafe`/`nimble` backends (no API key; `KEV_BASE_URL`, `KEV_MODEL` tune the
upstream). aarch64 note: PyPI's torch 2.8 wheel is CPU-only — install
`torch==2.8.0+cu129` from `download.pytorch.org` for CUDA (runs on GB10 via
PTX fallback). Measured: Kev-4B 95.9 % at 0.23 s/question in ~15 GiB bf16 —
fits next to the incumbent. Kev-27B (`--run jaredpalmer/kev-27b`, bf16-only)
scores **98.0 %** — ties Jev — at 1.1 s/question in ~63 GiB, which does *not*
fit beside the vLLM incumbent on this box (~120 GiB unified); benchmarking it
required stopping `vllm-qwen.service` first. Both variants share the shipped
fine-tune loop as their differentiator.

### `laya` — convaiinnovations/laya in-process

```bash
pip install laya
LAYA_MODEL_DIR=~/models/laya-typed-decisions \
    S1_BACKEND=laya python3 configs/s1_gateway.py
```

`laya.load(LAYA_MODEL_DIR)` at gateway startup; each request runs
`agent.predict(state, questions)` in a thread executor. Use the
`typed-decisions` checkpoint — the root checkpoint is tuned for guardrails and
scores near-chance on this suite. Non-autoregressive scorer: reports input
tokens only (0 output by construction). Measured 73.5 % on CPU — the GPU slot
was occupied by the incumbent service.

### Adding a backend

An adapter is one `async def handle(request, body)` in
`configs/s1_gateway.py`, registered in `HANDLERS`. Rules:

1. **Translate faithfully.** Map options to the model's native choice type;
   never let the adapter decide the answer itself.
2. **Disclose fallbacks.** Anything the model cannot natively do (free text,
   abstentions) needs a stated policy — like the token-candidate trick for
   open questions — written into the run's report notes.
3. **Map real usage.** Report the backend's own token counts; zeros read as
   "not reported", never as free.

## Workflow — swap the model, keep the application

```bash
# 1. Serve the candidate the way it wants to be served (vLLM, llama.cpp, …)
#    e.g. vLLM serving Bespoke-Nimble-9B on :8001
# 2. Point the gateway at it
S1_BACKEND=proxy S1_UPSTREAM=http://localhost:8001/v1 \
    python3 configs/s1_gateway.py
# 3. Nothing else changes: apps keep base_url=http://localhost:8123/v1
```

To return to Jev: `S1_BACKEND=typesafe` (or just run
`configs/typesafe-jev-shim.py`) with `TYPESAFE_API_KEY` set.

## Workflow — benchmark a candidate against the Jev baseline

Same URL, same transport, same suite — the only thing that varies is the model:

```bash
# candidate serving behind :8123 via whichever backend fits
./bench run --suite system1 --samples 2 \
    --label "candidate-x s1" \
    # BENCH_BASE_URL=http://localhost:8123/v1 BENCH_MODEL=<id /v1/models reports>
./bench report results/2026-09-30/typesafe-jev-1-13-s1.json \
    results/<date>/candidate-x-s1.json \
    --title "candidate-x vs Jev baseline on system1" \
    --question "Should candidate-x replace Jev behind the s1 endpoint?" \
    --verdict "..."
```

Decision criteria, in order:

1. **Contract conformance** — malformed/verbose replies fail the suite, so the
   accuracy number *is* the "application works as expected" check.
2. **Accuracy** — wins only if the 95 % Newcombe margin excludes zero;
   otherwise call it at-par and decide on cost.
3. **Cost** — seconds and output tokens per question against Jev's
   0.3 s / 38 tok.
4. **Operability** — does it run on this machine next to what else is served?

A candidate that clears all four replaces Jev behind the endpoint; the
baseline file and report stay as the historical reference.

## Failure semantics worth knowing

- The gateway answers `502` when its upstream fails and `400` when the prompt
  is not the s1 shape — the bench records both as generation failures, never
  as model wrongness.
- One upstream call per generation: concurrency comes from the runner
  (`BENCH_CONCURRENCY`, default 4), not request batching.
- Latency through the `typesafe` backend is hosted-service latency (WAN
  round-trip); latency through `proxy` is the local server's. Compare speed
  within a backend class, or say which you mixed.
