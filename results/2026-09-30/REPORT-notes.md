## Analysis — Bespoke-Nimble-9B and Laya on `system1` (issue #104)

Both candidates were served on side ports and driven through the same
OpenAI-compatible transport as the incumbent (`benchkit` harness, `system1`
suite, `--samples 2`, n=98 per arm).

### Serving what was actually measured

- **Nimble** (`BENCH_MODEL=nimble`) is the LoRA adapter
  `bespokelabs/Bespoke-Nimble-9B` (165 MiB, rank 16) hot-loaded by vLLM over the
  bf16 `Qwen/Qwen3.5-9B` base — `configs/nimble-9b-lora.sh`. The `nimble-9b`
  served name aliases the *base* weights; the adapter answers to `nimble`.
  Measuring `nimble-9b` would have silently measured the base model.
- **Laya** (`BENCH_MODEL=laya`) runs behind `laya-shim.py` (CPU-only aiohttp
  shim on :8804) that parses the suite's `State:/Question:/Options:` prompt,
  calls `Router().predict`, and emits the winning option's letter as a one-token
  streamed reply — `configs/laya-9b-shim.sh`. The reference `Router().predict`
  API is non-conversational; the shim is the only bridge, and its output is
  what the scorer sees.

### What the numbers say

- **Nimble think-OFF ties the incumbent exactly**: 96.9 % vs 96.9 % with
  identical Wilson bounds — the margin's interval includes zero by
  construction. It does so at 0.4 s/task and 2 output tokens versus the
  incumbent's 0.7 s / 4 tokens. On accuracy alone there is nothing to choose.
- **Nimble think-ON scores 0.0 %** (CI 0.0–3.8, n=98, zero errors, zero
  truncations). Every generation completed — the adapter produced ~308 tokens
  of reasoning per question and never emitted an exact-match answer. This is
  a measured product difference, not a harness failure: Nimble is a
  non-deliberative decision head and `enable_thinking` removes it from that
  product entirely. The incumbent under thinking still scores 93.9 %.
- **Laya scores 67.3 % in both modes** (CI 57.6–75.8). The encoder ignores the
  thinking kwarg, so both runs are the same measurement. Misses concentrate on
  questions whose `options` are absent (open short answers the typed router
  cannot represent — a known ~2-pt ceiling) plus several ordinary `choice`
  misses; Laya's own checkpoint also warns that some choice heads ship
  uncalibrated temperatures. At ~0.4–0.5 s/task on CPU it is cheap, but it is
  ~30 points behind.

### Machine constraints measured along the way

- bf16 `Qwen3.5-9B` + LoRA needs ~22.6 GiB (`--gpu-memory-utilization 0.19`).
  With the incumbent at ~72 GiB and ~22 GiB held by another process, ~20 GiB
  free was not enough — the sidecar only fits with the primary stopped. These
  numbers were run with the incumbent offline; `configs/nimble-9b-merged.sh`
  documents the standalone fallback.
- `Intel/Qwen3.5-9B-int4-AutoRound` (~8.4 GiB) loaded fine at util 0.12 in the
  squeezed pool; LoRA-over-quantized init was interrupted before a verdict.
- llama.cpp serves Qwen3.5 GGUFs natively, but `convert_lora_to_gguf.py` fails
  on this hybrid arch (`NotImplementedError` in `_reorder_v_heads`, on
  `attn_gate`/`ssm_*` tensors) — no GGUF-LoRA path without converter work.

### Verdict

Keep the incumbent. Nimble-OFF matches its accuracy cheaper but is a
different, narrower product — it collapses under thinking, needs the base's
GPU budget, and its adapter serves no other suite here. Laya is ~30 points
behind and cannot represent open questions. Neither displaces
`montimage-dgx-spark`; Nimble is recorded as a viable specialist decision
endpoint for environments that can spare ~23 GiB and never enable thinking.
