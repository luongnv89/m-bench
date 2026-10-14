## Analysis

**Harness:** benchkit's built-in loop for every row. Same endpoint (`:8001` router, alias
`montimage-dgx-spark`), same 0.62 / 32 GiB-KV memory pin, 2 samples per task.
Incumbent: `configs/qwen3.6-35b-a3b-nvfp4.sh` (live launcher). Candidate:
`configs/lfm2.5-24b-a2b-fp8.sh` — official `LiquidAI/LFM2.5-24B-A2B-FP8` checkpoint,
`--reasoning-parser qwen3 --tool-call-parser lfm2`, model-card sampling
(temp 0.1, top_k 50, repetition_penalty 1.05), no speculative decoding (no MTP head).

| Arm | Qwen3.6-35B-A3B NVFP4 | LFM2.5-24B-A2B FP8 |
|---|---|---|
| `all` think-OFF (6k budget) | **82.1 %** (70.2–90.0), 826 out-tok, 0 trunc | 60.7 % (47.6–72.4), 3,917 out-tok, **23 trunc** |
| `all` think-ON (16k budget) | **82.1 %**, 6,711 out-tok, 3 trunc | 71.4 % (58.5–81.6), 6,412 out-tok, 4 trunc |
| `agentic-hard` OFF | **93.8 %** (71.7–98.9), 1,146 out-tok, valid calls 96 % | 87.5 % (64.0–96.5), 4,993 out-tok, valid calls 81 % |
| `agentic-hard` ON | **93.8 %**, 2,230 out-tok, valid calls 96 % | 87.5 %, 4,789 out-tok, valid calls 77 %, 2 turn-limit hits |
| Decode speed (per stream, conc. 4) | 44–47 tok/s (MTP k=2) | 27–28 tok/s |

**Caveats.**

- **LFM2.5 has no think-OFF mode.** Its chat template opens `<think>` on every
  assistant turn and ignores `enable_thinking`, so the OFF arms measure the same
  always-reasoning model under a 6k budget. The 23 truncations there are the budget,
  not the model's code — this −21.4 pp margin *does* clear its Newcombe interval
  (lower bound ≈ +4.7 pp), but it is a budget effect: a client that caps output at 6k
  will see exactly this. The fair one-shot comparison is the ON arm: −10.7 pp, and the
  95 % intervals overlap, so this margin alone is not decisive at n=56.
- **Agentic margins are noise** (−6.3 pp, n=16 each, intervals overlap almost entirely).
- **Speed is a serving-stack number, not a model ceiling.** vLLM picked DeepGEMM FP8
  block kernels on GB10 with no FlashInfer autotune cache; no NVFP4 checkpoint and no
  MTP drafter exist yet (Liquid lists a DSpark drafter as "coming soon", SGLang only).
- **"Stalled" = finished by plain text instead of the `finish` tool** (15/16 OFF, 6/16 ON
  for LFM2.5 vs 0/16 and 3/16 for Qwen). It is not a failure by itself but means the
  model ignores the loop's explicit finish protocol more often.
- Liquid states the model was RL-trained inside pi and OpenCode. A harness run
  (AGENTS.md step 6) could narrow the agentic gap; it was not run here.

## Verdict reasoning

Every arm points the same way: LFM2.5 scores lower (−10.7 pp one-shot ON, −6.3 pp
agentic), emits 2–4× more output tokens per agentic task, decodes ~40 % slower per
stream on this box, and makes more invalid tool calls (77–81 % vs 96 %). Only the
budget-bound think-OFF one-shot margin clears its confidence interval, but there is no arm where it wins on solve rate,
cost or reliability, and its only theoretical advantage — fewer active parameters —
does not show up as speed on this stack today.
