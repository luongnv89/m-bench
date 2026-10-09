## Scope and run selection

This partial System One comparison covers the current S1 incumbent (Kev-4B), the historical TypeSafe Jev baseline, and a fresh Cloudflare/clef-flash run. All use the same 49-question suite (`suite_hash` `79ff3d7d9b04330f6bae5fa8a723f8dbc93f0c229cb7a49b7df10ecf5fdb9fd0`) with two samples per question. The selected Clef-Flash run used the standard S1 gateway on temporary port 8124, bf16/CUDA, concurrency 4, and completed all 98 generations without transport errors.

The first Clef-Flash attempt (`clef-flash-9b-s1-2026-10-09.json`) had three initial 502s (`lazy wrapper should be called at most once`) during concurrent first-use initialization. After one sequential native request warmed the model, the repeat run completed with zero generation errors and reproduced the 98.0% score. The first raw result is preserved but excluded from the accuracy comparison as an initialization/harness failure, not model evidence.

## Serving constraints

The local Clef-Flash checkpoint is 17.75 GiB of safetensors and ran alongside the existing services. The cached release is commit `17f0b0ad64efb65d273590632833508766b2aae6`; comparison of all cached artifact hashes with Hugging Face's current `fde727a287004204b7518dcc983fe64379776712` found only `README.md` differs. The custom model source was inspected before import; it defines the model and loads safetensors, with no shell execution or dynamic code evaluation observed.

Cloudflare/clef is a 27B bf16 release with 51.19 GiB of weights (expected 55–65 GiB resident). With the active Qwen vLLM endpoint and Kev service, the box had about 40 GiB available after the Clef-Flash process exited, so the full Clef model was not loaded. Prior local notes report that it cannot coexist with the active vLLM endpoint. Measuring it requires taking the shared `vllm-qwen` service / `:8001` endpoint down temporarily; this was not authorized, so Clef remains unmeasured in this campaign.

The temporary `:8124` gateway was stopped after the run. The shared `:8001` and `:8123` endpoints remained responsive.