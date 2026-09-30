## Method notes — Kev-27B on system1 (issue #104 follow-up)

Kev-27B (`jaredpalmer/kev-27b`, github.com/jaredpalmer/kev) was measured
through the **same transport** as every s1 candidate: the standard gateway
(`configs/s1_gateway.py`) on `http://localhost:8123/v1` with
`S1_BACKEND=kev`, which reuses `ask_systemone` verbatim against
`KEV_BASE_URL=http://localhost:8009/v1`, `KEV_MODEL=kev-latest`. Same suite,
same protocol as the Kev-4B run: `--suite system1 --samples 2`.

### Serving

- `uv run python -m kev.serve --run jaredpalmer/kev-27b --port 8009` in the
  same clone (`~/workspace/luongnv89/kev`), same `torch==2.8.0+cu129` venv —
  PTX JIT fallback on the sm_121 GB10, bf16, CUDA.
- No quantized kev-27b artifact exists on the Hub: full bf16 weights,
  ~51 GB over 11 safetensors shards, 62.9 GiB measured on the GPU
  (weights + context + prefix cache).
- **It does not coexist with the incumbent.** With vLLM (67.6 GiB) and the
  mon-image app (21.9 GiB) resident, only ~5.6 GiB was free. The benchmark
  required stopping `vllm-qwen.service` and Kev-4B first (human-approved),
  leaving ~90 GiB free; the mon-image app was left running throughout.
  vLLM was restored after the run.

### Measurement

- `./bench run --suite system1 --samples 2` → 98 generations, concurrency 4.
- Result: **98.0 %** (95 % CI 92.9–99.4), 1.1 s/question — an exact tie with
  Jev (98.0 %, CI 92.9–99.4) and Nimble-9B (98.0 %), and 2.1 pp above Kev-4B
  (95.9 %).
- Failed generations (2/98): `error_log/q1` twice (answered `no`, expected
  `cannot determine`) — the same epistemic-abstention question that accounts
  for **all** of Jev's and Kev-4B's failures. Kev-27B fixed `spam_email/q2`,
  Kev-4B's only other miss, so its failure set is now identical to Jev's.
- Latency is ~4.8× Kev-4B's (1.1 s vs 0.23 s per question) and ~4× Jev's
  hosted-WAN 0.27 s — the price of 6.75× the weights on the same GPU, still
  under 2 s/question. Usage accounting caveat from the Kev-4B run applies
  unchanged (~52 in / 61 out vs Jev's rendered-prompt numbers).

### Context vs other candidates

On accuracy evidence Kev-27B joins Jev and Nimble-9B at the top of the
suite; on this corpus it is the strongest *local* s1 backend measured. But
it cannot run next to the incumbent on this machine — 62.9 GiB + 67.6 GiB
vLLM + 21.9 GiB mon-image exceeds the ~120 GiB unified pool — so it is a
candidate only on a host where the shared endpoint is down or moved, or for
a dedicated-typed-decisions deployment. Kev-4B remains the only variant
that fits **alongside** everything (15 GiB).
