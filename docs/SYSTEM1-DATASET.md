# System One dataset v3 (default `system1`)

`system1` is v3: **200 scenarios, one question each, ten families, every
question with listed options**. A full run is **200 calls at `--samples 1`**.
`system1-v3` is an alias (the name its first runs used). v2 stays runnable as
`system1-v2`, and v1 as `system1-legacy`. Scores from different versions are
not comparable; `suite_hash` tells them apart.

## Budget: 200 calls per arm

v2 cost 800 calls per arm (400 questions × 2 samples). v3 cuts that by
design, without dropping scenarios:

- **One question per scenario.** v2's second question usually restated the
  first decision's reason (the rule ID behind an action, the queue behind a
  priority, the signal behind a phishing verdict). v3 asks for both in one
  answer, such as `reject — R6`, `P2, security queue` or
  `quarantine — sender domain mismatch`. One call must get the decision and
  its reason right, which is the scenario-level scoring v2 lacked. `billing`
  asks the action only, and `evidence` asks the single most diagnostic of the
  two authored claims per record (`EVIDENCE_ASKED`).
- **One sample.** On v2, Jev gave the same answer on both samples for 384 of
  400 questions, so a second sample bought little. Variation in wording is
  measured by the paraphrase pairs instead, which test something real.

With 200 scored items, a 95 % Wilson interval is about ±5 pp near 85 %.
Margins smaller than that are noise. Add distinct scenarios rather than
samples when a decision is close.

## Why v3

v2's measured results (`results/2026-10-09-system1-v2-*`) showed that about 75 %
of the gap between Jev (79.5 %) and Qwen3.6 with thinking on (98.6 %) came from
five families that need multi-step calculation, not judgment: `time` (UTC
offset conversion), `money` (cent rounding at off-by-one boundaries),
`inventory` (stock sums), `events` (state-machine replay) and `records` (exact
joins plus open answers). Every single-pass model failed the same `time` cases,
the ones where the clock text and the instant disagree. A model that can think
aloud solves those by calculating. They measure System Two, and nine of v2's
ten answer keys come from about 20 lines of reference code. In production that
code runs before the decision model is called.

v3 measures the part a decision model is for:

- **Quantities are precomputed.** "Bought 45 days ago", "expired 10 minutes
  ago", "net received €1,250.00". No timestamps, no cents arithmetic, no joins
  (pinned by `test_no_computation_left_in_states`).
- **Facts arrive in prose.** Customer emails, chat transcripts, staff notes,
  console lines. The model must extract them.
- **Claims are not confirmations.** Customer-reported vs staff-confirmed damage,
  suspected vs confirmed security issues, requested vs completed revocations,
  pending vs approved grants, "I paid" vs bank-confirmed money.
- **Some cases cannot be decided yet.** `request inspection`, `request proof`
  and `wait for bank` are correct answers.
- **Untrusted text can carry instructions.** The `injection` family plants
  overrides in customer text, résumés, reviews and documents. Some plants push
  the correct answer, so always contradicting the plant does not work.
- **Every question has options.** Typed `choice` backends can reach every answer.
  This removes v2's 64-candidate shim, under which 3 `records` answers could not
  be won.

| Family | Cases | Built from | Distinction tested |
|---|---:|---|---|
| `returns` | 10 × 2 | rule logic | Recalls, proof of purchase, claimed vs confirmed damage, final sale, demands and promises from other staff |
| `triage` | 10 × 2 | rule logic | Confirmed vs suspected security, ongoing vs resolved vs staging outages, "URGENT" noise |
| `access` | 10 × 2 | rule logic | Explicit denies, project boundaries, approved vs pending vs expired grants, viewers with grants |
| `credentials` | 10 × 2 | rule logic | Completed vs requested vs suggested revocation, precomputed validity, maintenance now vs scheduled vs finished |
| `billing` | 10 × 2 | rule logic | Bank-confirmed vs claimed payment, pending transfers, written disputes, overpayment |
| `routing` | 10 × 2 | hand-authored | Act-on vs mentioned topics, multi-intent precedence, when a human is needed |
| `evidence` | 20 | hand-authored | Self-corrections, hedges and hearsay, plans and promises, time/place/item scope, quantifiers |
| `moderation` | 20 | hand-authored | Threats vs hyperbole, insults vs criticism, reported threats and self-harm |
| `phishing` | 20 | hand-authored | Authentication failures, lookalike domains, link mismatches vs authentic but risky requests |
| `injection` | 20 | hand-authored | Instructions inside untrusted content, including plants that agree with the correct answer |

`10 × 2` families render each base case twice, as a structured note and as
conversational prose. Both renderings share a `group` and have the same keys.

## Scoring

Per-question accuracy is still the headline and still ranks. On v3 it equals
scenario accuracy, because each scenario has one question. For s1 runs the
runner also records:

- `scenario_accuracy`: the share of (scenario, sample) pairs with every question
  right. It matters on v2, where sibling questions share a state.
- `group_accuracy`: the share of paraphrase pairs answered fully correctly in
  both renderings. A decision that changes when the case is reworded does not
  count. It is `None` on suites without groups (v2, legacy).

Difficulty labels are all `medium` until measured per-item accuracy can
calibrate them. v2 labelled by fixture position, which carried no information.

## Comparing decision models with reasoning models

Thinking on and thinking off are different products (see `AGENTS.md`). On a
System One workload, a reasoning arm spends seconds and hundreds of hidden
tokens per decision. Recommendation, not yet enforced by `bench report`: rank
System One candidates among arms that meet the decision contract (no hidden
reasoning, bounded output, sub-second latency). Report thinking-on arms beside
them as a System Two reference ceiling, with their latency and tokens.

## Promotion and current results

v3 became the default on 2026-10-10 after a blind annotation (400/400 keys
agreed on the 400-question draft, 15 wordings tightened) and a six-arm
measurement at 200 calls each (`results/2026-10-10-system1-v3-200/`):
gpt-6.1-sol medium 100.0, gpt-6-luna max 99.5, Qwen3.6 think-ON 97.0, Jev 95.5,
Qwen3.6 think-OFF 85.0, Kev-4B 71.0. The v3 roster is Jev, Kev-4B, Qwen with
thinking off and on, and frontier references through pi. Mercury Decide is
not on it.

Known limits: v3 is saturated at the frontier, and `moderation` and `triage`
are near 100 % for every strong arm. Add harder cases there before relying on
those families to separate decision models.

```bash
./bench validate --suite system1          # 200/200 data lint
python3 -m unittest tests.test_system1_v3_dataset
BENCH_BASE_URL=http://localhost:8123/v1 ./bench run --suite system1 \
    --samples 1 --concurrency 1 --label "jev system1-v3"   # 200 calls
```

---

# System One dataset v2 (`system1-v2`, reference)

v2 was the default `system1` from 2026-10-09 to 2026-10-10. Its result files
record the suite name `system1`; reproduce them with `--suite system1-v2`.

v2 contains **200 distinct scenarios and 400 scored questions**, with
20 scenarios and 40 questions in each of ten families. This is a dataset size,
not a repeat count: `--samples 1` makes 400 requests; `--samples 2` makes 800.
There are 380 multiple-choice questions and 20 open code-extraction questions.

The original suite had 23 scenarios and 49 questions. Multiple endpoints reached
98% on it, so it stopped separating their decision quality. It remains available
as `system1-legacy`, with the original state text, questions and answers intact.
Existing files under `results/` remain historical measurements of that dataset.

## What the new cases measure

| Family / task ID prefix | Cases | Distinction tested |
|---|---:|---|
| `policy` | 20 | Ordered exceptions, proof requirements, final sale and inclusive age limits |
| `triage` | 20 | Confirmed evidence, resolved versus ongoing outages, production scope and threshold precedence |
| `access` | 20 | Explicit denies, project boundaries, roles and restricted grants |
| `events` | 20 | Valid transitions, duplicate IDs, invalid events, unrelated orders and terminal states |
| `time` | 20 | Explicit UTC offsets, midnight crossings, inclusive start and exclusive expiry/maintenance end |
| `money` | 20 | Subtotal versus per-item rounding, half-up cents, shipping exclusions, credits and payment comparisons |
| `inventory` | 20 | Exact SKUs, active versus released reservations, arrival cutoffs and partial allocation |
| `dependencies` | 20 | Required versus optional dependencies, disabled jobs, resource limits and deterministic ties |
| `evidence` | 20 | Supported, refuted, conflicting and unknown evidence; negation, attribution and promised outcomes |
| `records` | 20 | Compound exact joins, numeric revisions, drafts, tombstones, conflicting and identical duplicates |

All rules and necessary facts are supplied in the state. These are bounded
operational decisions; no outside facts, live dates, tools or long-form output
are required. Irrelevant requests and near-matching records are deliberate
distractors. Many neighboring fixtures change a single fact across a decision
boundary. Correct option positions are deterministically shuffled per question.
The primary decision question in each family has no answer class above 60%.

The first four cases per family are labeled `medium`; the remaining sixteen
are `hard` (40 medium and 160 hard scenarios). These are design labels, not
measured difficulty estimates. A larger dataset alone does not prove that
saturation is solved: that requires fresh endpoint measurements.

## Ground truth and maintenance

`benchkit/suites/system1_v2.py` contains fixed fixtures and their explicit rules.
Nine families calculate answers from structured data using deterministic
reference logic, including decimal half-up rounding and timezone-aware datetimes.
The evidence family uses manually authored labels. Importing the module performs
no network access and draws no random fixtures. It is registered as
`system1-v2`.

`tests/test_system1_dataset.py` independently pins the primary answer of every
scenario and all numeric answers, checks representative secondary answers,
coverage, uniqueness, option scoring, deterministic reconstruction, decision
flips and preservation of the legacy fingerprint. These checks complement
the CLI data lint, which verifies schema and answer membership but cannot prove
semantic correctness. When adding cases, review both the facts and the key;
never weaken scoring to accommodate a model's response.

## Run and compare

```bash
./bench validate --suite system1-v2       # 200/200 data lint
./bench validate --suite system1-legacy   # 23/23 data lint
python3 -m unittest discover -s tests -p 'test_system1_dataset.py'

# Both models must use the standard :8123/v1 gateway; set BENCH_MODEL
# to the ID returned by /models for each backend before its run.
BENCH_BASE_URL=http://localhost:8123/v1 ./bench run --suite system1-v2 \
    --samples 2 --label "jev system1-v2 baseline"
BENCH_BASE_URL=http://localhost:8123/v1 ./bench run --suite system1-v2 \
    --samples 2 --label "candidate system1-v2"
./bench report results/<date>/jev-system1-v2-baseline.json \
    results/<date>/candidate-system1-v2.json \
    --title "System One v2 comparison" --question "Which endpoint should serve decisions?" \
    --verdict "<decision based on measured accuracy, latency and cost>"
```

Check the request budget before running hosted backends: two models with two
samples each require 1,600 successful requests, plus any upstream retries.
Normal endpoint restart approval rules still apply.

Re-measure the incumbent on v2. The historical 98% Jev score is a **legacy**
baseline, not a v2 baseline. `suite_hash` distinguishes the datasets and prevents
pooling their repeated runs, but that does not make different datasets valid
head-to-head comparisons. Use matching suite hashes, transport and run settings.

Report accuracy, failures, per-question latency and tokens, and inspect the
task IDs for family-specific weaknesses. Each family has equal question weight.
Sibling questions and cases sharing a template are correlated; the existing
Wilson intervals describe scored attempts, not independent coverage of real
workloads. Repeated `--samples` measure response variability and do not create
new cases. Close decisions need more distinct cases, repeated runs and inspection
of whether failures concentrate in one family. If v2 also approaches 100%, add
new failure-driven families rather than cosmetic parameter variants.
