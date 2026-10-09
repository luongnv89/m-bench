# The standard System One endpoint

One stable URL — `http://localhost:8123/v1` — serves every System One decision
workload on this machine. Applications and the `system1` bench suite code
against it once; **which model answers is a deployment detail** chosen by the
gateway's `S1_BACKEND`. Replacing Jev with a better decision model is an env
change and a restart, not an application change.

```
app / bench ──► :8123/v1 (OpenAI chat subset) ──► s1_gateway.py
                                                   │
                  S1_BACKEND ──────────────────────────────┤
                  │          │          │      │       │   │
               typesafe    nimble      laya   kev    clef proxy
                  │          │          │      │       │   │
            api.typesafe  ollama    in-process kev.  in-  S1_UPSTREAM
            /v1/systemone /v1/      predict()  serve proc.  (vLLM,
                          systemone          /v1/  jsm.    llama.cpp,
                                             systemone sys-  any OpenAI
                                                     temone  model)
```

## The contract

Transport: the OpenAI subset the s1 runner uses.

| Endpoint | Notes |
|---|---|
| `GET /v1/models` | backend's model list (proxied in `proxy` mode unless `S1_MODEL` pins a model) |
| `POST /v1/systemone` | native typed `state` / `questions` / `answers` contract in `systemone` mode |
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

The measurements in this section use the original 49-question suite, now
`system1-legacy`. The default `system1` is v2 (200 scenarios / 400 questions).
Re-measure Jev on v2 before comparing a new candidate; historical scores cannot
serve as its baseline. See [the dataset design](SYSTEM1-DATASET.md).

`S1_BACKEND=typesafe` (the default) serves Jev — the measured reference every
candidate is compared against.

| Metric | Jev `jev-1.13.0` (`jev-latest`) |
|---|---|
| Accuracy on `system1-legacy` | **98.0 %** (95 % CI 92.9–99.4, n=98) |
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
| Kev-4B (Q4_K_M GGUF, llama.cpp master `/v1/systemone`) | `kev` | 95.9 % — inside noise | identical miss profile to `kev.serve` bf16; ~3 GiB, needs a build ≥ decision-model merge (PR #29818, 2026-10-02) |
| Clef-Flash-9B (`Cloudflare/clef-flash`, bf16) | `clef` | **98.0 %** — ties Jev | local, ~19 GiB measured; fits alongside everything — nothing stopped; only miss is `error_log/q1`, identical to Jev's; F1 1.000 on the phishing corpus with the strongest local noul on the hardest lure |

Mercury Decide `inception/mercury-decide:free` through `systemone`:
**98.0% (96/98)**, zero generation errors; **F1 1.000 on 16 phishing emails**
through the phishing service's `typesafe_only` pipeline. Measured mean latency:
2.64 s/system1 question (includes free-tier quota waits), 2.93 s/email.
This ties historical Jev, not a statistically established accuracy improvement;
the small suites are saturated. Hosted fallback supported, not installed as the
shared default. Report: `results/2026-10-01-mercury-decide-rerun/REPORT.md`.

Full comparison: `results/2026-09-30/REPORT-s1-candidates.md` (+ `NOTES-s1-candidates.md`);
Kev runs: `results/2026-09-30/REPORT-kev-s1.md` (+ `NOTES-kev-s1.md`),
`results/2026-10-01/REPORT-kev27b-s1.md` (+ `NOTES-kev27b-s1.md`),
`results/2026-10-02/REPORT-kev4b-llamacpp-s1.md` (+ `NOTES-kev4b-llamacpp-s1.md`);
Clef-Flash run: `results/2026-10-05/REPORT-clef-flash-s1.md` (+ `NOTES-clef-flash-s1.md`),
`results/2026-10-05/REPORT-s1-phishing-clef-flash.md`.

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

Forwards requests and streaming responses verbatim, except that an explicitly
set `S1_MODEL` overrides the client's model. For authenticated upstreams set
`S1_API_KEY`; client Authorization headers and other providers' keys are never
forwarded automatically. Trailing slashes on `S1_UPSTREAM` are accepted.
This is how a locally
served candidate — Bespoke-Nimble-9B on vLLM, a GGUF on llama.cpp, an ollama
model — answers behind the same URL Jev uses. Zero translation, zero drift:
the app sees the same wire contract, the model sees the same prompt.

### `systemone` — any native System One decision endpoint

Configure the **full request URL**, model, and upstream key once. Subsequently
swap compatible providers by changing these deployment settings only; no runner,
application, question, or scoring edits are needed. Both chat-shaped benchmark
requests and native TypeSafe SDK requests use the same upstream.

```bash
# OpenRouter Mercury Decide (NOT a chat-completions model)
# Export OPENROUTER_API_KEY from your .env securely first; do not commit it.
S1_BACKEND=systemone \
S1_DECISION_URL=https://openrouter.ai/api/alpha/decisions \
S1_MODEL=inception/mercury-decide:free \
S1_API_KEY="$OPENROUTER_API_KEY" \
    python3 configs/s1_gateway.py
```

For TypeSafe directly use `S1_DECISION_URL=https://api.typesafe.ai/v1/systemone`,
`S1_MODEL=jev-latest`, and `S1_API_KEY="$TYPESAFE_API_KEY"`. No provider-specific
adapter is required for an endpoint using the same schema. `S1_API_KEY` is
explicit, not guessed from the URL or loaded from `.env` by the gateway.

- `GET /v1/models` advertises the configured model (not a remote availability
  check). Prove availability with an actual decision request before benchmarking.
- Chat benchmark prompts use the same parsing and open-question state-token
  candidate fallback as Jev. Usage is mapped from real `input_tokens` and
  `output_tokens`; no synthetic confidence or answers are introduced.
- `POST /v1/systemone` forwards the native payload with the configured model,
  preserving all question types, calibrated probabilities, answers, and usage.
  This supports the phishing service's existing SDK without modifying its code:

```bash
# From anti-phishing-email-service; SDK appends /v1/systemone to this API root.
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8123 \
TYPESAFE_DEFAULT_MODEL=inception/mercury-decide:free \
    .venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only --split all \
    --output evaluation/results/mercury-decide.json
```

The gateway retries transient native decision failures at most three times and
reports upstream failures as 502, never as model answers. An explicitly exhausted
OpenRouter daily free quota is not retried by the gateway: its 429 and reset
metadata are preserved. For transient failures, numeric `Retry-After` and reported
`X-RateLimit-Reset` timestamps are respected; each wait is capped at 65 seconds.
Raising the daily allowance does not remove the observed 20 requests/minute free
model limit. The system1 runner disables redundant OpenAI SDK retries;
other runners are unchanged. Reasoning on/off flags are not applicable to these
prefill-only typed decision endpoints.

Budget requests before starting: v2 `system1` has 400 questions, so `--samples 2`
needs 800 successful calls per model. `system1-legacy` has 49 questions and needs
98 calls at two samples. The full phishing corpus adds 16 calls, plus smoke
checks and retries. A fresh 50-request daily free allowance cannot cover either.
Quota limits may vary: check the API's current allowance rather than assuming
this observed limit is universal. Capture benchmark stdout to a fresh log file
(e.g. `./bench run ... | tee candidate-run.log`), since final JSON is written only
when the run finishes.

**Do not restart a shared gateway without approval.** For a non-disruptive run,
start a temporary gateway with `S1_PORT=8124` and point both clients at that port.
The adapter and prompts are identical; disclose the port difference in reports.
Stop only your temporary process afterward.

API reference used: <https://openrouter.ai/openapi.json>,
`POST /api/alpha/decisions` (`DecisionsRequest` / `DecisionsResponse`).

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

### `clef` — Cloudflare/clef(-flash) in-process

```bash
CLEF_REPO=Cloudflare/clef-flash S1_BACKEND=clef \
    python3 configs/s1_gateway.py      # needs torch+transformers (the kev venv)
```

The release ships `joint_schema_model.py`; the gateway loads it at startup
(`snapshot_download` + `load_release_model`, bf16 on `CLEF_DEVICE`, default
cuda) and runs its `systemone(model, processor, body)` in a thread executor —
it consumes a `/v1/systemone` request natively, so the adapter is one line
and the native `/v1/systemone` route forwards verbatim (the phishing SDK
needs no changes). `CLEF_REPO` takes any clef release (`Cloudflare/clef` for
the 27B) or a local dir. Deps beyond aiohttp: torch, transformers 5.x, and
`torchvision` for the AutoProcessor's video backend — on aarch64/GB10 the
PyPI CPU wheel (0.23.0) works with torch 2.8.0+cu129; there is no aarch64
CUDA torchvision wheel. Prefill-only scorer: reports input tokens only.
Measured: clef-flash ~19 GiB resident, coexists with the incumbent; clef-27B
(~55-65 GiB) cannot — benchmarking it needs the vLLM endpoint stopped.

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
# incumbent serving behind :8123; set BENCH_MODEL to its /models ID
./bench run --suite system1 --samples 2 --label "jev system1-v2 baseline"
# candidate serving behind the same URL; set BENCH_MODEL to its /models ID
./bench run --suite system1 --samples 2 \
    --label "candidate-x system1-v2" \
    # BENCH_BASE_URL=http://localhost:8123/v1 BENCH_MODEL=<id /v1/models reports>
./bench report results/<date>/jev-system1-v2-baseline.json \
    results/<date>/candidate-x-system1-v2.json \
    --title "candidate-x vs Jev baseline on system1" \
    --question "Should candidate-x replace Jev behind the s1 endpoint?" \
    --verdict "..."
```

Decision criteria, in order:

1. **Contract conformance** — malformed/verbose replies fail the suite, so the
   accuracy number *is* the "application works as expected" check.
2. **Accuracy** — wins only if the 95 % Newcombe margin excludes zero;
   otherwise call it at-par and decide on cost.
3. **Cost** — seconds and output tokens per question against Jev measured
   on the same current suite.
4. **Operability** — does it run on this machine next to what else is served?

A candidate that clears all four replaces Jev behind the endpoint; the
baseline file and report stay as the historical reference.

## Failure semantics worth knowing

- The gateway answers `502` when its upstream fails, or `429` for confirmed
  OpenRouter daily quota exhaustion, and `400` when the prompt is not the s1
  shape. The bench records these as generation failures, never valid answers;
  do not interpret a transport-failure score as model accuracy.
- One upstream call per generation: concurrency comes from the runner
  (`BENCH_CONCURRENCY`, default 4), not request batching.
- Latency includes the upstream: local backends measure local serving, while
  TypeSafe, OpenRouter, and hosted proxy targets include WAN round-trip. Compare
  speed within a backend class, or say which you mixed.
