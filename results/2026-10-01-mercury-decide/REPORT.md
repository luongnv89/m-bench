# Mercury Decide via OpenRouter — incomplete benchmark campaign

## Decision

**Do not replace the incumbent based on this campaign.** The configurable native
endpoint works, but Mercury's benchmark did not finish: OpenRouter exhausted the
key's daily free-model allowance. No completed Mercury accuracy, confidence
interval, ranking, or phishing F1 is available. Re-run a fresh complete campaign
once sufficient allowance is available; do not splice this successful prefix into
another run or silently substitute a paid Mercury/chat model.

## Measured and observed status

| Evaluation | Model and harness | Status |
|---|---|---|
| system1 incumbent | `kev-latest`, benchkit via existing s1 gateway | Complete: 94/98 correct, 95.9%; 0 generation errors |
| system1 candidate | `inception/mercury-decide:free`, benchkit via temporary s1 gateway | Incomplete: 67 passing sample outcomes observed in live command output before quota failures; no final JSON |
| phishing candidate | `inception/mercury-decide:free`, anti-phishing service `typesafe_only` evaluator | Not started; system1 timeout prevented reaching this step |

The 67 passing outcomes are an **order-dependent successful prefix**, not a
completed 100% accuracy score, and not a count of upstream HTTP requests. The
partial run's question responses and exact timings were not serialized before
the outer 600-second command timeout; only the live command output captured the
passing prefix. Do not manufacture a candidate result JSON from it. Two samples
repeat the same 49 questions; they are not 98 independent task types.

The incumbent's persisted artifact is `incumbent-s1.json`: 49 questions, two
samples each, concurrency 1. Its mean measured latency was 0.491 s/question and
mean upstream-reported usage was 52.06 input / 60.96 output tokens per question.
It missed `spam_email/q2` and `error_log/q1` in both samples. The live gateway
advertises `kev-latest`; no checkpoint size is inferred from that alias.

## Compatibility checks

- Exact model's chat-completions probe returned 400: this is a decision model;
  OpenRouter explicitly requires `/api/alpha/decisions`.
- Native decision probe returned 200 with a correct `blue` choice, probabilities,
  confidence, usage, and resolved model `inception/mercury-decide-20260930`.
- Native response shape is the same System One shape used by TypeSafe's SDK:
  `state`, typed `questions`, and typed `answers`.
- OpenRouter's ordinary `/api/v1/models` catalog did not list this decision model.
  Gateway `/v1/models` advertises the pinned model; availability was established
  by the successful native request, not by assuming catalog presence.
- Source contract: `https://openrouter.ai/openapi.json`,
  `POST /api/alpha/decisions`, `DecisionsRequest` / `DecisionsResponse`.

## Configuration and transport

Candidate:

```text
S1_BACKEND=systemone
S1_DECISION_URL=https://openrouter.ai/api/alpha/decisions
S1_MODEL=inception/mercury-decide:free
S1_API_KEY=<OPENROUTER_API_KEY loaded from local .env; never recorded>
S1_PORT=8124
BENCH_BASE_URL=http://localhost:8124/v1
```

The existing shared gateway on :8123 was left running, advertising `kev-latest`
with backend `kev`, upstream `http://localhost:8009/v1`. Candidate measurements
used the **same standard gateway implementation** on temporary port :8124 to
avoid a shared restart; this port difference is the only local transport change.
No shared serving endpoint was restarted. The temporary process is no longer
running. Existing `.env` and task tests were not modified.

Chat-shaped system1 prompts used the unchanged parsing, questions and scoring.
Open short-answer questions retain Jev's documented choice-over-state-tokens
fallback. Native phishing requests would forward all three typed questions
(noul, choice, score) and calibrated answers without translation or invented
confidence. Thinking modes are not applicable to the native decision API.
Hosted Mercury latency includes WAN and any retries; the incumbent is local.
No Mercury speed aggregate is published from this unfinished run.

Suite fingerprint (same system1 dataset validated for the candidate):
`79ff3d7d9b04330f6bae5fa8a723f8dbc93f0c229cb7a49b7df10ecf5fdb9fd0`.

## Commands attempted

```bash
./bench run --suite system1 --samples 2 --concurrency 1 \
  --base-url http://localhost:8123/v1 --model kev-latest \
  --label "incumbent kev-latest s1" --keep-code \
  --out results/2026-10-01-mercury-decide/incumbent-s1.json

./bench run --suite system1 --samples 2 --concurrency 1 \
  --base-url http://localhost:8124/v1 --model inception/mercury-decide:free \
  --label "mercury-decide-free s1" --keep-code \
  --out results/2026-10-01-mercury-decide/mercury-s1.json
```

The second command was interrupted by the outer timeout and did not write
`mercury-s1.json`. A sequential phishing command was prepared but never executed:

```bash
# cwd: /home/montimage/workspace/anti-phishing-email-service
TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:8124 \
TYPESAFE_DEFAULT_MODEL=inception/mercury-decide:free \
SEMANTIC_BACKEND_FALLBACK=false \
  .venv/bin/python scripts/performance_benchmark.py \
  --benchmarks variant_comparison --variants typesafe_only --split all \
  --output <fresh-absolute-result-path>/mercury-phishing.json
```

This is the repository's adjudicated seed corpus (16 emails: 9 phishing,
7 benign), not private mailbox data. No external repository code was changed.
Historical Jev phishing results are not presented as fresh measurements.

## Blocker and recovery

A direct diagnostic after the timeout returned:

```json
{
  "status": 429,
  "message": "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day",
  "limit_source": "openrouter_free_tier_daily",
  "X-RateLimit-Limit": "50",
  "X-RateLimit-Remaining": "0",
  "X-RateLimit-Reset": "1790899200000"
}
```

That reset is **2026-10-02 00:00 UTC**. The reported allowance and the 67 observed
passing sample outcomes are recorded as observed; this campaign cannot explain
that discrepancy. Do not infer a general allowance from the successful prefix.

98 system1 calls + 16 phishing calls = **at least 114 successful candidate calls**,
plus smoke checks and transient retries. A fresh allowance of 50 cannot cover
this whole campaign. OpenRouter's response recommends a credit top-up to raise
the daily allowance; the user must do that themselves, or plan separate runs
across resets. No credit purchase or paid model fallback was authorized or made.

After this incident the gateway was changed to preserve explicit daily-quota
429 metadata and not retry that terminal condition. The system1 client disables
redundant SDK retries; transient gateway retries remain bounded. These refinements
are covered by offline tests; no additional quota-consuming validation was done.

## Validation

- Editable install succeeded.
- One-shot references: 28/28 pass.
- Agentic oracles: 16/16 pass.
- System1 data lint: 23/23 pass.
- Full offline unit suite: 434 tests run, OK (6 skipped).
- New gateway tests cover native typed payloads, streaming, model pinning,
  authentication isolation, preserved daily-quota errors, transient retry bounds,
  and existing System One upstream compatibility.
