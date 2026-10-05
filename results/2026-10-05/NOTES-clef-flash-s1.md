## Method notes — Clef-Flash-9B on system1 (issue #104 follow-up)

Cloudflare/clef-flash was measured through the **same transport** as every s1
candidate: the standard gateway (`configs/s1_gateway.py`) — on temporary
`http://localhost:8124/v1` per the no-restart rule — with the new
`S1_BACKEND=clef`. Same suite, same protocol as all prior runs:
`--suite system1 --samples 2`, 98 generations, concurrency 4.

`Cloudflare/clef` (27B, bf16, ~55-65 GiB) was the requested candidate, but it
cannot load next to the incumbent vLLM endpoint (~70 GiB) and Kev-4B (~15 GiB)
on this ~120 GiB box — only ~27 GiB was free. The human chose the smaller
`Cloudflare/clef-flash` (9B, Qwen3.5-9B backbone, bf16, 17.5 GiB weights) to
avoid taking :8001 down. The two releases share the same
`joint_schema_model.py` loader, so the `clef` backend measures either via
`CLEF_REPO`; only the weights differ.

### Serving

- New `clef` backend in `configs/s1_gateway.py`: loads the release in-process
  at startup (`snapshot_download` + `joint_schema_model.load_release_model`,
  bf16 on CUDA), runs `joint_schema_model.systemone(model, processor, body)`
  in a thread executor — it consumes a `/v1/systemone` request body natively,
  so the adapter is one line of translation. The native `/v1/systemone` route
  forwards verbatim for the phishing service's TypeSafe SDK.
- Ran inside the kev venv (`torch 2.8.0+cu129`, `transformers 5.17.0`,
  aiohttp) on the GB10 via PTX fallback. `AutoProcessor` additionally needed
  `torchvision==0.23.0` (aarch64 CPU wheel — the video processor's backend;
  no aarch64 CUDA wheel exists on the cu129 index). Installed into the kev
  venv, additive only.
- Resident footprint: ~19 GiB — fit **alongside** the incumbent vLLM
  endpoint, Kev-4B, and the :8123 gateway, all left running. No endpoint was
  stopped or restarted.

### Measurement

- `./bench run --suite system1 --samples 2` → **98.0 %** (95 % CI 92.9–99.4),
  0.6 s/question, 14 s wall, 160 in / 0 out tokens per question.
- Failed generations (2/98): `error_log/q1` twice (answered `no`, expected
  `cannot determine`) — the same epistemic-abstention question that accounts
  for all of Jev's, Kev-27B's and Mercury Decide's misses. **Identical
  failure set to Jev.**
- Usage accounting: clef is a prefill-only joint-head scorer, so
  `output_tokens` is 0 by construction (same convention as laya); the
  reported 160 input tokens are clef's own tokenizer count of the encoded
  record, not the rendered chat prompt — same caveat class as kev's
  ~52 in / 61 out.
- Open questions (no `options:` block) go through the gateway's documented
  state-token-candidate fallback, unchanged — clef's `systemone()` requires
  non-empty choice criteria, so the same policy applies.

### Context vs other candidates

Clef-Flash joins Jev, Nimble-9B, Kev-27B and Mercury Decide at 98.0 % — the
suite's effective ceiling. Its differentiator is the fit: it is the *largest*
top-tier candidate that coexists with the incumbent endpoint (Kev-27B needed
vLLM stopped; Nimble-9B needs Ollama; Mercury needs OpenRouter quota).
At 0.6 s/question it is ~2× slower than Kev-4B (0.23 s) and hosted Jev
(0.3 s WAN), still far inside any decision budget.
