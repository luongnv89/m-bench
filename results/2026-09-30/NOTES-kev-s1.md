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
