# Notes — Kev-4B GGUF via llama.cpp /v1/systemone

## Setup

Kev-4B was served as a Q4_K_M GGUF by llama.cpp's new native decision-model
endpoint (PR ggml-org/llama.cpp#29818, merged 2026-10-02):

```
bench system1 → :8123 s1_gateway (S1_BACKEND=kev) → llama-server :8080 /v1/systemone
```

The gateway parses each rendered s1 prompt into `(state, question, options)` and
posts one `choice` question to llama.cpp's `/v1/systemone` — the same adapter
path used for the earlier `kev.serve` bf16 measurement
(`results/2026-09-30/kev-4b-s1.json`). The only thing that changed is the serving
stack: PyTorch bf16 readout → llama.cpp Q4_K_M readout.

## llama.cpp build note

The GGUF is a *decision model* (`{arch}.decision.type` metadata, embedding
readout, no text generation). It cannot be loaded by llama.cpp builds that
predate the decision-model merge:

- brew `llama.cpp` 0.5.0 (b11146) and release b11351 both fail with
  `done_getting_tensors: wrong number of tensors; expected 428, got 426`.
- A source build of master (`bed0a85`) loads it and logs
  `init: decision model type: kev`. Server reports the model natively on
  `/v1/systemone` with calibrated per-option probabilities and a `confidence`
  field.
- Build wrinkle on master: `tools/ui` asset provisioning needs a real UI
  version. Fix used here: `HF_UI_VERSION=b11351 cmake -B build
  -DLLAMA_UI_GZIP=OFF` (prebuilt UI bundle exists for b11351; the gzip pass has
  a bug reading asset paths).

## Measurements

- Accuracy 95.9% (n=98, 2 samples/question), 0 truncated, 0 errored.
- ~0.6 s/question, 52 input tokens, 0 output tokens (prefill-only readout).
- Identical miss profile to the bf16 `kev.serve` run: `spam_email/q2` (both
  samples, answered "yes" on a no) and `error_log/q1` (both samples — the
  epistemic "cannot determine" case that Jev also misses).
- Memory footprint: ~3 GiB GGUF vs ~15 GiB bf16 for `kev.serve`.

## Caveats

- Q4_K_M vs bf16: quantization did not move the score on this suite (same 4/98
  misses, same questions), but the suite is saturating — a harder decision set
  could separate them.
- `output_tokens` is 0 by construction (pointer readout); token cost is not
  comparable to a generative backend.
