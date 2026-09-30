# Nimble vs Jev on the real phishing corpus — live comparison

Real-use-case benchmark of `typesafe_analyzer`'s classifier arm run against
two System One backends on the adjudicated corpus (16 samples: 9 phishing,
7 benign, `--split all`), same machine, same day, same scoring path. This is
the deployment question from m-bench issue #104 replayed on production code:
**can a local Nimble replace hosted Jev behind `typesafe_analyzer`?**

## Method

Nimble required **zero code changes** — it implements the same
`/v1/systemone` contract (noul + choice + score), so the swap was environment
variables only:

```bash
# Jev arm (baseline) — real TypeSafe API
.venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only \
    --split all --output eval-jev.json

# Nimble arm — same analyzer, same questions, local Ollama 0.35 backend
TYPESAFE_BASE_URL=http://localhost:11434 TYPESAFE_DEFAULT_MODEL=nimble \
    .venv/bin/python scripts/performance_benchmark.py \
    --benchmarks variant_comparison --variants typesafe_only \
    --split all --output eval-nimble.json
```

`typesafe_analyzer` passes only `api_key` + `timeout` to
`AsyncTypeSafeClient`; the SDK resolves `TYPESAFE_BASE_URL` /
`TYPESAFE_DEFAULT_MODEL` from the environment. Any `TYPESAFE_API_KEY` value
satisfies the analyzer's presence check — Ollama ignores the bearer.

## Headline

| Arm | Backend | F1 | Precision | Recall | Avg latency | p95 |
|---|---|---|---|---|---|---|
| `typesafe_only` → Jev `jev-1.13.0` | hosted TypeSafe API | **1.000** | 1.000 | 1.000 | **0.31 s** | 0.35 s |
| `typesafe_only` → Nimble (Q8_0 ~9.5 GiB) | local Ollama :11434 | 0.941 | 1.000 | 0.889 | 0.77 s | 0.78 s |
| `llm_only` → gpt-oss-120b (context) | hosted Groq | 1.000 | 1.000 | 1.000 | 1.49 s | 2.16 s |

Nimble: 15/16 — one false negative, zero false positives. Jev and the
incumbent LLM: 16/16. The corpus is small, so one miss is −5.9 F1 points;
read the gap as a signal, not a settled margin.

## The miss — `phish-soc-001`

"Mandatory password reset — action required" from
`it-helpdesk@corp-itdesk.example.com` (a credential-harvesting lure). Raw
typed answers from the same `_build_state` payload:

| Judgment | Jev | Nimble |
|---|---|---|
| `is_phishing` noul | **0.710** → phishing | **0.042** → benign |
| `threat_type` choice | credential_harvesting (0.96) | credential_harvesting (0.76) |
| `severity` score /5 | 3.0 | 0.10 |
| upstream usage | 970 in / 133 out | 2463 in / 4 out |

Nimble's miss is an **internal inconsistency**: its choice head calls the
email credential harvesting at 0.76 while its noul head calls it benign at
0.04. Jev's three judgments agree.

The same inconsistency shows on benign mail: Nimble's `threat_type` returns
`credential_harvesting` on samples where its own noul is ~0.01–0.04
(`ben-txn-001`, `ben-biz-002` probed), while Jev returns `unknown`. The
phishing verdict is gated by noul ≥ 0.5 so detection is unaffected, but
`threat_type` feeds `ReportGenerator` mitigation text — a Nimble backend
would attach credential-harvesting mitigations to emails it scored benign.

## Latency and cost

Per email (all three typed questions in one `system_one` call; samples are
evaluated sequentially, so wall time is the honest throughput number):

| Backend | avg | median | p95 | wall (16 emails) | throughput |
|---|---|---|---|---|---|
| Jev (hosted TypeSafe API) | **0.31 s** | 0.29 s | 0.35 s | 5.0 s | 3.19 emails/s |
| Nimble (local Ollama 0.35, GB10) | 0.77 s | 0.76 s | 0.78 s | 12.3 s | 1.30 emails/s |
| gpt-oss-120b (hosted Groq) | 1.49 s | 1.60 s | 2.16 s | 23.9 s | 0.67 emails/s |

- Jev's 0.31 s/question is **hosted WAN latency**; Nimble's 0.77 s is local
  inference on the GB10 next to the incumbent vLLM service. Nimble is ~2.4×
  slower but still well inside the analyzer's 30 s timeout and faster than
  the incumbent LLM (1.49 s).
- The harness `cost` block reports *estimated* tokens (identical 797 in per
  arm — an estimator over email text, not upstream usage). Real upstream
  usage per call, from the probe: Jev ~970 in / ~133 out; Nimble ~2.4k in /
  ~4 out (its prompt render includes the full question schema).
- Nimble runs with no API key and sends no email content off the machine —
  a privacy property Jev cannot offer.

## Caveats

- 16 samples; one miss moves F1 by ~6 points. The committed live baseline
  (`typesafe_vs_llm_live.md`) shows Jev at F1 1.0 with 0.63 s avg — this
  run's 0.31 s reflects WAN variance, not a different model (`jev-1.13.0`
  both times).
- `risk_score` magnitudes rose across the board since the committed live
  file (benign ~0.05 → ~0.33 on both backends today) — downstream
  `EnhancedRiskCalculator` drift in the repo, identical for both arms;
  detection verdicts are the comparable signal.
- Nimble's severity Score compression (0.10 vs Jev's 3.0 on the same email)
  tracks its noul judgment — both are the same underlying miss, not two
  independent errors.

## Verdict

**Keep Jev as primary; Nimble is a viable hot-spare, not a replacement —
yet.** The swap story is proven end-to-end: the same `typesafe_analyzer`
code, questions and scoring path ran unchanged against a local model and
produced typed judgments the pipeline consumed with zero adaptation. But on
the real corpus Nimble missed a credential-harvesting lure its own choice
head identified, and its threat-type head is inconsistent on benign mail —
both fixable-by-checkpoint issues, worth re-testing when a new Ollama build
lands. For air-gapped or no-key deployments it already beats having no
System One backend at all: 15/16 with zero false alarms.
