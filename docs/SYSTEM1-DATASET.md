# System One dataset v2

`system1` now contains **200 distinct scenarios and 400 scored questions**, with
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
no network access and draws no random fixtures. `system1.py` exports this default
dataset through the existing runner contract.

`tests/test_system1_dataset.py` independently pins the primary answer of every
scenario and all numeric answers, checks representative secondary answers,
coverage, uniqueness, option scoring, deterministic reconstruction, decision
flips and preservation of the legacy fingerprint. These checks complement
the CLI data lint, which verifies schema and answer membership but cannot prove
semantic correctness. When adding cases, review both the facts and the key;
never weaken scoring to accommodate a model's response.

## Run and compare

```bash
./bench validate --suite system1          # 200/200 data lint
./bench validate --suite system1-legacy   # 23/23 data lint
python3 -m unittest discover -s tests -p 'test_system1_dataset.py'

# Both models must use the standard :8123/v1 gateway; set BENCH_MODEL
# to the ID returned by /models for each backend before its run.
BENCH_BASE_URL=http://localhost:8123/v1 ./bench run --suite system1 \
    --samples 2 --label "jev system1-v2 baseline"
BENCH_BASE_URL=http://localhost:8123/v1 ./bench run --suite system1 \
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
