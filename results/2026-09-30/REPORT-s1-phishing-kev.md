# Kev vs Jev on the real phishing corpus — live comparison

Real-use-case benchmark of `typesafe_analyzer`'s classifier arm run against
three System One backends on the adjudicated corpus (16 samples: 9 phishing,
7 benign, `--split all`), same machine (GB10), same scoring path. Follows the
Nimble run in `nimble_vs_jev_live.md`: **can a local Kev-4B replace hosted
Jev behind `typesafe_analyzer`?**

## Method

Kev required **zero code changes** — `kev.serve` implements the same
`/v1/systemone` contract (noul + choice + score), so the swap was environment
variables only:

```bash
# Kev arm — local kev.serve :8009 (jaredpalmer/kev-4b, Qwen3.5-4B + LoRA r16, bf16)
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8009 \
TYPESAFE_DEFAULT_MODEL=kev-latest \
    .venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only \
    --split all --output evaluation/results/eval-kev.json
```

`typesafe_analyzer` passes only `api_key` + `timeout` to
`AsyncTypeSafeClient`; the SDK resolves `TYPESAFE_BASE_URL` /
`TYPESAFE_DEFAULT_MODEL` from the environment. Jev and Nimble numbers are the
earlier arms from `nimble_vs_jev_live.md`, re-listed for comparison.

## Headline

| Arm | Backend | F1 | Precision | Recall | Avg latency | p95 |
|---|---|---|---|---|---|---|
| `typesafe_only` → Jev `jev-1.13.0` | hosted TypeSafe API | **1.000** | 1.000 | 1.000 | **0.31 s** | 0.35 s |
| `typesafe_only` → Kev-4B (bf16 ~15 GiB) | local kev.serve :8009 | **1.000** | 1.000 | 1.000 | 0.35 s | 0.46 s |
| `typesafe_only` → Nimble (Q8_0 ~9.5 GiB) | local Ollama :11434 | 0.941 | 1.000 | 0.889 | 0.77 s | 0.78 s |
| `llm_only` → gpt-oss-120b (context) | hosted Groq | 1.000 | 1.000 | 1.000 | 1.49 s | 2.16 s |

Kev: 16/16 — zero false positives, zero false negatives, matching Jev and the
hosted LLM. The corpus is small, so read margins as signal, not settled
gaps (one flip = −5.9 F1 points).

## The hardest sample — `phish-soc-001`

"Mandatory password reset — action required" from
`it-helpdesk@corp-itdesk.example.com` (a credential-harvesting lure) — the one
sample Nimble missed. Raw typed answers from the same `_build_state` payload:

| Judgment | Jev | Nimble | Kev-4B |
|---|---|---|---|
| `is_phishing` noul | **0.710** → phishing | **0.042** → benign | **0.493** → borderline |
| `threat_type` choice | credential_harvesting (0.96) | credential_harvesting (0.76) | unknown (soc. eng. 0.32) |
| `severity` score /5 | 3.0 | 0.10 | 2.09 |

Three different failure/consistency shapes:

- **Jev** — all three judgments agree: confident phishing.
- **Nimble** — internally inconsistent: choice head says credential
  harvesting at 0.76 while noul says benign at 0.04; severity near zero
  leaves no evidence for the pipeline to work with → false negative.
- **Kev** — internally consistent but borderline: noul sits just under the
  0.5 analyzer gate (0.493), threat type declines to pick an attack category
  (top non-`unknown`: social_engineering 0.32), severity is a middling 2.09.
  The analyzer's own verdict is `is_phishing=False` (risk 0.35) — yet the
  harness recorded it **phishing** because `EnhancedRiskCalculator`
  aggregates the analyzer's severity/threat evidence to 0.75, above the
  unsafe boundary. The pipeline, not the noul, made this call.

That last point matters for a swap decision: Kev's *detection record* is
perfect on this corpus, but on its hardest sample the phishing probability
is a coin flip. Where Nimble failed loudly (contradictory heads), Kev is
quietly uncertain — a candidate for the repo's fine-tune loop
(`skills/kev-finetune`) if soc-001-style lures matter.

## Latency and cost

Per email (all three typed questions in one `system_one` call; samples are
evaluated sequentially, so wall time is the honest throughput number):

| Backend | avg | median | p95 | wall (16 emails) |
|---|---|---|---|---|
| Jev (hosted TypeSafe API) | **0.31 s** | 0.29 s | 0.35 s | ~5.0 s |
| Kev-4B (local, GB10) | 0.35 s | 0.31 s | 0.46 s | ~5.5 s |
| Nimble (local Ollama, GB10) | 0.77 s | 0.76 s | 0.78 s | ~12.3 s |
| gpt-oss-120b (hosted Groq) | 1.49 s | 1.60 s | 2.16 s | ~23.9 s |

- Kev is the fastest *local* backend measured — 2.2× faster than Nimble and
  within ~12 % of Jev's hosted WAN latency, fully offline, no API key.
- Estimated tokens for the arm: 4,859 total (797 in / 4,062 out — the
  pipeline's own estimate, counting the serialized `llm_analysis` block as
  output, not upstream usage).
- Serving note: kev.serve on this box needed `torch==2.8.0+cu129` from
  download.pytorch.org (PyPI's aarch64 wheel is CPU-only); runs on the GB10
  via PTX fallback at ~15 GiB next to the incumbent vLLM service.

## Verdict

Kev-4B is a viable drop-in local backend for `typesafe_analyzer` on this
corpus: detection identical to Jev (16/16), local latency within noise of
the hosted API, consistent (never contradictory) judgments. Nimble's earlier
miss is now the weakest arm on both accuracy and speed. Two caveats: n=16
keeps any single flip worth ~6 F1 points, and Kev's borderline noul on
soc-001 means the pipeline's evidence aggregation — not the classifier
verdict — made the correct call on the hardest sample. If `typesafe_analyzer`
moves to raw-noul gating, re-measure before swapping.
