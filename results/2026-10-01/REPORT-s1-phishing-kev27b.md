# Kev-27B vs Jev on the real phishing corpus — live comparison

Real-use-case benchmark of `typesafe_analyzer`'s classifier arm run against
the adjudicated corpus (16 samples: 9 phishing, 7 benign, `--split all`),
same machine (GB10), same scoring path. Follows `kev_vs_jev_live.md` and
`nimble_vs_jev_live.md`: **can a local Kev-27B replace hosted Jev behind
`typesafe_analyzer`?**

## Method

Same zero-code-change swap as the Kev-4B arm — `kev.serve` implements the
`/v1/systemone` contract natively, so only the environment differs:

```bash
# Kev-27B arm — local kev.serve :8009 (jaredpalmer/kev-27b, bf16, 62.9 GiB)
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8009 \
TYPESAFE_DEFAULT_MODEL=kev-latest \
    .venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only \
    --split all --output evaluation/results/eval-kev27b.json
```

Serving constraint, unlike the 4B arm: Kev-27B ships bf16-only (~51 GB
weights) and needs ~63 GiB — it could **not** run next to the incumbent
vLLM service (67.6 GiB) on this ~120 GiB unified-memory box. The run
required stopping `vllm-qwen.service` and Kev-4B first (approved for this
benchmark); vLLM was restored afterward. Jev / Nimble / Kev-4B numbers are
the earlier arms, re-listed for comparison.

## Headline

| Arm | Backend | F1 | Precision | Recall | Avg latency | p95 |
|---|---|---|---|---|---|---|
| `typesafe_only` → Jev `jev-1.13.0` | hosted TypeSafe API | **1.000** | 1.000 | 1.000 | **0.31 s** | 0.35 s |
| `typesafe_only` → Kev-4B (bf16 ~15 GiB) | local kev.serve :8009 | **1.000** | 1.000 | 1.000 | 0.35 s | 0.46 s |
| `typesafe_only` → Kev-27B (bf16 ~63 GiB) | local kev.serve :8009 | **1.000** | 1.000 | 1.000 | 1.71 s | 2.07 s |
| `typesafe_only` → Nimble (Q8_0 ~9.5 GiB) | local Ollama :11434 | 0.941 | 1.000 | 0.889 | 0.77 s | 0.78 s |
| `llm_only` → gpt-oss-120b (context) | hosted Groq | 1.000 | 1.000 | 1.000 | 1.49 s | 2.16 s |

Kev-27B: 16/16 — zero false positives, zero false negatives. Detection is
identical to Jev, Kev-4B and the hosted LLM; the corpus is small, so read
margins as signal, not settled gaps (one flip = −5.9 F1 points).

## The hardest sample — `phish-soc-001`

"Mandatory password reset — action required" from
`it-helpdesk@corp-itdesk.example.com` (a credential-harvesting lure) — the
sample that separated the backends on the 4B run. Raw typed answers from the
same `_build_state` payload:

| Judgment | Jev | Nimble | Kev-4B | Kev-27B |
|---|---|---|---|---|
| `is_phishing` noul | **0.710** → phishing | **0.042** → benign | 0.493 → borderline | 0.471 → borderline |
| `threat_type` choice | credential_harvesting (0.96) | credential_harvesting (0.76) | unknown (soc. eng. 0.32) | credential_harvesting (0.44) |
| `severity` score /5 | 3.0 | 0.10 | 2.09 | 2.91 |

Kev-27B is *more* correct in shape but *not* in the noul: its phishing
probability (0.471) sits even a touch below Kev-4B's (0.493) — still under
the 0.5 analyzer gate — yet it now names the right attack category
(`credential_harvesting`, where 4B declined with `unknown`) and scores
severity 2.91 vs 2.09. The analyzer's own verdict is again
`is_phishing=False` (risk 0.43), and `EnhancedRiskCalculator` aggregates the
threat/severity evidence to **0.97** — decisively above the unsafe boundary,
versus 4B's knife-edge 0.75. Same mechanism as the 4B arm (the pipeline, not
the noul, makes the call), but with a much wider margin.

## Latency and cost

Per email (three typed questions in one `system_one` call; sequential
samples, so wall time is the honest throughput number):

| Backend | avg | median | p95 | wall (16 emails) |
|---|---|---|---|---|
| Jev (hosted TypeSafe API) | **0.31 s** | 0.29 s | 0.35 s | ~5.0 s |
| Kev-4B (local, GB10) | 0.35 s | 0.31 s | 0.46 s | ~5.5 s |
| Nimble (local Ollama, GB10) | 0.77 s | 0.76 s | 0.78 s | ~12.3 s |
| gpt-oss-120b (hosted Groq) | 1.49 s | 1.60 s | 2.16 s | ~23.9 s |
| Kev-27B (local, GB10) | 1.71 s | 1.58 s | 2.07 s | ~27.4 s |

- Kev-27B is the **slowest** arm measured — ~5× Kev-4B and ~5.5× Jev — the
  direct price of 6.75× the weights on the same GPU (bf16, PTX fallback on
  sm_121). Still well inside any per-email budget that tolerates 2 s.
- Estimated tokens for the arm: 4,909 total (797 in / 4,112 out — the
  pipeline's own estimate, not upstream usage).
- Serving note, as before: `torch==2.8.0+cu129` from download.pytorch.org;
  runs on the GB10 via PTX fallback. Footprint 62.9 GiB — requires the
  shared vLLM endpoint to be down; Kev-4B (15 GiB) is the variant that fits
  alongside everything.

## Verdict

Kev-27B matches Jev's detection on this corpus (16/16, F1 1.000) with
*cleaner internal judgments* than Kev-4B on the hardest sample — correct
attack category, higher severity — but its noul is not actually better
(0.471 vs 0.493) and it costs ~5× the latency plus a 63 GiB footprint that
excludes co-hosting with the incumbent endpoint. On this machine Kev-4B
remains the better trade: identical detection record, 5× faster, and it
fits next to the existing services. Kev-27B makes sense only for a
dedicated typed-decisions host — and on either variant, soc-001-style
borderline lures stay a fine-tune target (`skills/kev-finetune`), since the
pipeline's evidence aggregation is what makes the call.
