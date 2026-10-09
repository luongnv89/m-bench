# Cloudflare Clef candidate comparison — local System One suite

## Method

All candidate runs used the validated 49-question `system1` suite, two samples per question (98 generations), the built-in bench runner, and the same standard S1 gateway implementation. The current Kev-4B run and historical Jev run are included as references. The selected Clef-Flash run followed a sequential warm-up because its initial cold concurrent attempt triggered three `lazy wrapper should be called at most once` 502s; that initial raw JSON is preserved separately and excluded from the comparison. The warmed run had zero generation errors.

## Measured results

- **Cloudflare/clef:** 98.0% (96/98; 95% Wilson CI 92.9–99.4), 1.9 s/question, 160 input / 0 output tokens. Its two misses were `error_log/q1`, matching the Jev and Clef-Flash failure set.
- **Cloudflare/clef-flash:** 98.0% (96/98; 95% Wilson CI 92.9–99.4), 0.7 s/question, 160 input / 0 output tokens; same two misses.
- **Current Kev-4B incumbent:** 95.9% (94/98; 95% Wilson CI 90.0–98.4), 0.2 s/question.
- **Historical TypeSafe Jev reference:** 98.0% (96/98; same suite hash), 0.3 s/question.

At 98%, the suite has little power to distinguish these decision models; neither Clef size demonstrates an accuracy win over Clef-Flash or historical Jev. The margin between either Clef variant and current Kev is within uncertainty.

## Serving and revision

Clef was loaded offline from the cached release in the `kev` venv (torch 2.8.0+cu129, Transformers 5.17.0) through a temporary S1 gateway on `:8124`. The user's approved `vllm-qwen.service` user unit was stopped only for this run; the separate `:8001` router stayed running (and returned unavailable while its backend was stopped), while S1 `:8123` continued serving `kev-latest`. Clef's scored run and warm-up completed, its temporary gateway was stopped, and Qwen was restarted. Restoration was verified by the original model list, healthy router/backend, a successful `:8001` inference returning `OK`, and the unchanged `:8123` Kev model list. Before/after service snapshots are `cloudflare-clef-27b-s1-warmed-20261009T053334Z-before.txt` and `cloudflare-clef-27b-s1-warmed-20261009T053334Z-after.txt`.

The latest Hugging Face refs are `Cloudflare/clef` `ed3eed331870db2eff4b0db01237128ede8a00ce` and `Cloudflare/clef-flash` `fde727a287004204b7518dcc983fe64379776712`. The offline cached snapshots were `2f3de3dd85f379784083b0814d997ab627200f0c` and `17f0b0ad64efb65d273590632833508766b2aae6`; content-hash comparison found only README.md differs from the respective latest refs. Both repos' Python model source was inspected before import; it defines the architecture and loads safetensors, with no shell execution or dynamic evaluation observed.

Clef's BF16 weight files total 51.19 GiB and the measured workload required taking Qwen offline; Clef-Flash has 17.75 GiB of weights and ran alongside the existing services. For a Cloudflare Clef deployment on this machine, prefer **Clef-Flash**: it matched Clef's score and ran faster with a substantially smaller footprint. This does not establish a statistically significant reason to replace the current Kev incumbent.