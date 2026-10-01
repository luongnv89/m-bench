# Mercury Decide — completed endpoint and workload evaluation

## Decision

**Keep Mercury Decide as a supported, configuration-only hosted backend, but do
not replace the faster local incumbent by default.** It satisfies the native
System One contract and matches the historical Jev system1 result. Its small
accuracy advantage over today's `kev-latest` baseline is inside statistical
noise, while OpenRouter's free-tier throttling adds substantial latency.

## Headline — measured on this machine

| Dataset / harness | Model | Result | Mean measured latency |
|---|---|---|---|
| system1 / benchkit, standard s1 gateway | `inception/mercury-decide:free` | **96/98 correct, 98.0%**, Wilson 95% CI 92.9–99.4%; zero generation errors | **2.64 s/question**, includes upstream retries and quota waits |
| phishing corpus / anti-phishing service `typesafe_only` pipeline | `inception/mercury-decide:free` | **16/16 correct, F1 1.000**, precision 1.000, recall 1.000; zero analyzer failures | **2.93 s/email**, p95 **4.81 s** |
| system1 / benchkit, existing gateway (earlier today) | `kev-latest` | **94/98 correct, 95.9%**, zero generation errors | **0.49 s/question** |

The phishing confusion matrix is **TP=9, TN=7, FP=0, FN=0**. All 16 native
analyzer calls succeeded, with fallback disabled. This score belongs to Mercury
through the phishing service's existing parse/analyze/risk-score pipeline, **not**
to an independently scored raw noul probability. The risk calculator is part of
that harness, just as it was for earlier Jev/Kev comparisons.

The two system1 misses are both samples of `error_log/q1`: Mercury answered `no`,
where the expected answer is `cannot determine`. This is the same failure as
historical Jev; Mercury correctly answered `spam_email/q2`, which the current
`kev-latest` baseline missed.

**These suites are saturated at this capability level.** 98% on system1 and a
perfect result on only 16 phishing emails do not establish a perfect model or a
reliable generalization advantage. Harder decision and phishing cases are needed.
The two system1 samples repeat 49 questions; the sample count is not a count of
independent problem types. Historical Jev numbers in the generated comparison
are explicitly historical, not a fresh rerun of that hosted provider.

## Native API compatibility and configuration

Mercury is a decision model and rejects chat completions. The OpenRouter native
endpoint implements the same `state` / typed `questions` / `answers` schema as
TypeSafe System One. A smoke call resolved the requested free model to
`inception/mercury-decide-20260930` and returned real choice probabilities,
confidence, and usage with cost 0.

```text
S1_BACKEND=systemone
S1_DECISION_URL=https://openrouter.ai/api/alpha/decisions
S1_MODEL=inception/mercury-decide:free
S1_API_KEY=<updated OPENROUTER_API_KEY loaded securely from local .env>
S1_PORT=8124
```

The standard gateway ran on temporary **:8124**, not the shared :8123 endpoint,
to avoid an unapproved restart. Same implementation and prompts, different
listen port only. The shared Kev gateway remained running throughout. No serving
restart, model substitution, paid-model fallback, or external repository source
edit occurred. Keys are absent from result files and logs.

The chat-shaped system1 adapter uses the same option translation and documented
choice-over-state-tokens fallback for open questions as Jev. Native phishing
requests preserve all three question types (noul, choice, score), criteria,
calibrated probabilities and answers. No synthetic confidence is introduced.
Reasoning on/off flags are not applicable to this decision endpoint.

## Free-tier rate limiting and corrective rerun

The updated key authenticated successfully with `is_free_tier=false`. That did
**not** remove the free model's **20 requests/minute** limit.

The first run with the updated key is retained as `mercury-s1.json`. It finished
with 87/98 correct, but **9 generation failures were per-minute 429 throttling**,
not wrong decisions. Do not use its 88.8% end-to-end result as model accuracy or
pool it with the corrected run. The rate error explicitly reported
`limit_source=openrouter_free_tier_per_minute` and a millisecond reset timestamp.

The gateway was then corrected to respect numeric `Retry-After` and the reported
`X-RateLimit-Reset`, with each wait capped at 65 seconds and at most three total
attempts. Explicit daily quota exhaustion still fails without gateway retries;
SDK retries remain disabled for system1. A **fresh complete run**, not a patched
or selectively repaired result, produced `mercury-s1-rateaware.json`: 98 outcomes,
zero transport errors, zero truncation, wall time **258.87 seconds**.

All previous runs, including the earlier daily-quota interruption, remain
untouched. The successful phishing run does not require repeating: all 16 calls
completed without errors before the rate-aware system1 rerun.

## Latency and cost interpretation

- System1 mean upstream usage: **81.96 input / 2.91 output tokens** per question.
- System1 time includes quota waiting/retries; it is operational end-to-end
  latency, not unthrottled model inference time.
- Phishing mean pipeline latency **2.926 s**, median **3.199 s**, p95 **4.810 s**,
  total **46.809 s** for 16 emails.
- Phishing token totals in its artifact (**797 input / 4,128 output**) are the
  pipeline's **estimates**, not upstream native API usage. Do not directly compare
  them with system1's reported tokens or infer billing from them.
- OpenRouter's exact requested model is the `:free` variant; the smoke API reported
  cost 0. No paid Mercury model was selected. This campaign does not measure
  costs for a paid deployment.
- Mercury requires no local model weights/GPU memory, but depends on hosted
  availability, WAN latency, allowance, and throttling. Local Kev latency and
  hosted Mercury latency are different serving classes.

## Artifacts and reproducibility

- `mercury-s1-rateaware.json`: authoritative corrected system1 run.
- `system1-rateaware.log`: full corrected progress output.
- `mercury-phishing.json`: authoritative phishing evaluator run.
- `phishing.log`: evaluator log.
- `smoke.json`: real native response identifying the resolved model.
- `mercury-s1.json`, `system1.log`: retained throttled first rerun, excluded from
  the quality comparison.
- Incumbent: `../2026-10-01-mercury-decide/incumbent-s1.json`.
- Historical Jev: `../2026-09-30/typesafe-jev-1-13-s1.json`.

System1 fingerprint:
`79ff3d7d9b04330f6bae5fa8a723f8dbc93f0c229cb7a49b7df10ecf5fdb9fd0`.

Phishing source repo: `/home/montimage/workspace/anti-phishing-email-service`,
HEAD `1cf84d88284732364a0e3fd423d0a9d8ccd2494c`. Seed corpus path:
`tests/fixtures/corpus`; split `all` (16 adjudicated fixture emails, not mailbox
messages). SHA-256 over sorted relative paths plus file contents, separated by
NULs: `7db3b6afe296088b0b2f787ff9efb4a7f5c00728bd0c0615b4aa0a80d361179b`.

Bench checkout base commit: `3fb5a4e69ba95c5da2021129f7958e4eba296342`, with the
native gateway and rate-limit changes in the working tree.

```bash
# Temporary gateway configured as above; capture output to a new log.
./bench run --suite system1 --samples 2 --concurrency 1 \
  --base-url http://localhost:8124/v1 --model inception/mercury-decide:free \
  --label "mercury-decide-free s1 rate-aware" --keep-code \
  --out <fresh-path>/mercury-s1-rateaware.json

# cwd: anti-phishing-email-service
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8124 \
TYPESAFE_DEFAULT_MODEL=inception/mercury-decide:free \
SEMANTIC_BACKEND_FALLBACK=false \
  .venv/bin/python scripts/performance_benchmark.py \
  --benchmarks variant_comparison --variants typesafe_only --split all \
  --output <fresh-absolute-path>/mercury-phishing.json
```

Validation before the campaign: 28/28 references, 16/16 agentic oracles,
23/23 system1 lint. Offline tests also cover quota/reset handling, retry bounds,
auth isolation, and typed-question preservation. Task tests and scoring were not
changed to obtain these results.
