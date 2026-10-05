# Clef-Flash-9B vs Jev on the real phishing corpus — live comparison

Real-use-case benchmark of `typesafe_analyzer`'s classifier arm run against
the adjudicated corpus (16 samples: 9 phishing, 7 benign, `--split all`),
same machine (GB10), same scoring path. Follows `kev_vs_jev_live.md`,
`nimble_vs_jev_live.md`, `kev27b` and `mercury-decide`: **can a local
Cloudflare/clef-flash replace hosted Jev behind `typesafe_analyzer`?**

## Method

Same zero-code-change swap, but through the standard s1 endpoint — clef's
release ships `joint_schema_model.py`, whose `systemone()` consumes a
`/v1/systemone` request natively, so a temporary `s1_gateway.py` on :8124
(`S1_BACKEND=clef`) serves both the bench suite and the SDK with no
translation layer at all:

```bash
# Clef-Flash arm — in-process via s1 gateway :8124 (Cloudflare/clef-flash, bf16, ~19 GiB)
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8124 \
TYPESAFE_DEFAULT_MODEL=clef-flash \
    .venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only \
    --split all --output evaluation/results/eval-clef-flash.json
```

Serving: kev venv (`torch 2.8.0+cu129`, `transformers 5.17.0`, plus
`torchvision==0.23.0` for the AutoProcessor video backend) on the GB10 via
PTX fallback. ~19 GiB resident — ran **alongside** the incumbent vLLM
endpoint, Kev-4B and the shared :8123 gateway; nothing was stopped.
`Cloudflare/clef` (27B) could not be benchmarked the same way without
endpoint downtime — deferred.

## Headline

| Arm | Backend | F1 | Precision | Recall | Avg latency | p95 |
|---|---|---|---|---|---|---|
| `typesafe_only` → Jev `jev-1.13.0` | hosted TypeSafe API | **1.000** | 1.000 | 1.000 | **0.31 s** | 0.35 s |
| `typesafe_only` → **Clef-Flash-9B** (bf16 ~19 GiB) | local s1 gateway :8124 | **1.000** | 1.000 | 1.000 | 0.47 s | 0.48 s |
| `typesafe_only` → Kev-4B (bf16 ~15 GiB) | local kev.serve :8009 | **1.000** | 1.000 | 1.000 | 0.35 s | 0.46 s |
| `typesafe_only` → Kev-27B (bf16 ~63 GiB) | local kev.serve :8009 | **1.000** | 1.000 | 1.000 | 1.71 s | 2.07 s |
| `typesafe_only` → Nimble (Q8_0 ~9.5 GiB) | local Ollama :11434 | 0.941 | 1.000 | 0.889 | 0.77 s | 0.78 s |
| `typesafe_only` → Mercury Decide (free) | hosted OpenRouter | **1.000** | 1.000 | 1.000 | 2.93 s | 4.81 s |
| `llm_only` → gpt-oss-120b (context) | hosted Groq | 1.000 | 1.000 | 1.000 | 1.49 s | 2.16 s |

Clef-Flash: 16/16 — zero false positives, zero false negatives, all 16
analyzer calls succeeded (no fallback). Detection is identical to Jev, both
Kev variants, Mercury and the hosted LLM; the corpus is small, so read
margins as signal, not settled gaps (one flip = −5.9 F1 points).

## The hardest sample — `phish-soc-001`

"Mandatory password reset — action required" from
`it-helpdesk@corp-itdesk.example.com` (a credential-harvesting lure) — the
sample that separated every backend so far. Raw typed answers from the
same `_build_state` payload:

| Judgment | Jev | Nimble | Kev-4B | Kev-27B | **Clef-Flash** |
|---|---|---|---|---|---|
| `is_phishing` noul | **0.710** → phishing | **0.042** → benign | 0.493 → borderline | 0.471 → borderline | **0.730** → phishing |
| `threat_type` choice | credential_harvesting (0.96) | credential_harvesting (0.76) | unknown (soc. eng. 0.32) | credential_harvesting (0.44) | **credential_harvesting (0.72)** |
| `severity` score /5 | 3.0 | 0.10 | 2.09 | 2.91 | **3.05** |

Clef-Flash is the strongest local read on this lure measured to date: the
**only local backend whose noul clears the 0.5 analyzer gate unaided**
(0.730 — edging Jev's own 0.710), while also naming the right attack
category at 0.72 confidence and scoring severity 3.05. Every other local
arm — Kev-4B, Kev-27B — needed `EnhancedRiskCalculator` to carry a
borderline noul over the line; Nimble missed outright. Final verdict:
`predicted_phishing=true`, risk 1.0.

## Latency and cost

Per email (three typed questions in one `system_one` call; sequential
samples, so wall time is the honest throughput number):

| Backend | avg | median | p95 | wall (16 emails) |
|---|---|---|---|---|
| Jev (hosted TypeSafe API) | **0.31 s** | 0.29 s | 0.35 s | ~5.0 s |
| Kev-4B (local, GB10) | 0.35 s | 0.31 s | 0.46 s | ~5.5 s |
| **Clef-Flash (local, GB10)** | **0.47 s** | 0.46 s | 0.48 s | **~7.5 s** |
| Nimble (local Ollama, GB10) | 0.77 s | 0.76 s | 0.78 s | ~12.3 s |
| gpt-oss-120b (hosted Groq) | 1.49 s | 1.60 s | 2.16 s | ~23.9 s |
| Kev-27B (local, GB10) | 1.71 s | 1.58 s | 2.07 s | ~27.4 s |
| Mercury Decide (hosted OpenRouter, free) | 2.93 s | — | 4.81 s | ~46.8 s |

- 0.47 s/email with a 0.48 s p95 — the tightest latency spread measured;
  ~1.3× Kev-4B, ~1.5× Jev, still comfortably inside any per-email budget.
- Estimated tokens for the arm: 4,942 (797 in / 4,145 out — the pipeline's
  own estimate; clef's real usage is input-only, 0 output tokens by
  construction).
- Resident ~19 GiB: the only top-tier local backend that fits **beside**
  the incumbent vLLM endpoint + Kev-4B — nothing was stopped for this arm.

## Verdict

Clef-Flash-9B matches Jev's detection on this corpus (16/16, F1 1.000) with
the *cleanest internal judgments* of any local arm — the only one whose
noul beats the 0.5 gate unaided on the hardest lure — at 0.47 s/email and a
~19 GiB footprint that coexists with everything else on the box. On pure
measured evidence it is the best local `typesafe_analyzer` backend here:
Nimble misses a lure, both Kevs need pipeline rescue on it, and Kev-27B
cannot even stay resident. The caveats are the suite's, not the model's:
n=16 is saturated (one flip ≈ 6 F1 points), and the 27B clef — the card's
flagship — remains unmeasured pending endpoint downtime.
