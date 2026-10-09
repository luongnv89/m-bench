# Method notes — Kev-4B vs TypeSafe Jev on `system1` v2

Campaign: `results/2026-10-09-system1-v2-kev4b-vs-jev` (Devin worker `devin-s1`).
Suite: `system1` v2 — 200 scenarios / 400 scored questions, ten families of
20 scenarios x 2 questions each. 380 multiple-choice + 20 open questions
(`records_*/q2`). Data lint `200/200` and `23/23` (legacy) re-verified on this
working tree before the runs. Uncommitted v2 dataset files used as instructed;
no benchmark code, questions, keys, scoring or tests touched.

## Measured arms

| Arm | Model (as served) | Backend | Where it runs |
|---|---|---|---|
| Kev-4B | `kev-latest` → `jaredpalmer/kev-4b` (LoRA-16 pointer head on `Qwen/Qwen3.5-4B-Base`, **bf16, torch, cuda**, temp 2.41) | `kev` | `kev.serve` systemd unit `kev-4b.service` on :8009 — already serving, ~15 GiB class |
| Jev | `jev-latest` → **`jev-1.13.0`** (reported per response) | `typesafe` | hosted `https://api.typesafe.ai/v1/systemone` — WAN latency included |

## Transport: one URL, both arms, no shared-service changes

Both arms went through the **same `configs/s1_gateway.py` build at the same URL
`http://localhost:8124/v1`**, run sequentially. :8124 is a *temporary gateway
this worker started* (docs' suggested port for non-disruptive runs):

1. `S1_BACKEND=kev S1_PORT=8124 KEV_BASE_URL=http://localhost:8009/v1 KEV_MODEL=kev-latest` → Kev arm.
2. Same process stopped; `S1_BACKEND=typesafe S1_PORT=8124 TYPESAFE_API_KEY=<from anti-phishing-email-service/.env>` → Jev arm.

The shared `s1-gateway.service` on :8123 (kev backend), `kev-4b.service` on
:8009, `vllm-qwen.service` on :8801 and `ollama-nimble.service` were **queried
but never restarted, reconfigured or stopped**. PIDs of my gateway processes:
1372719 (kev arm), 1375257 (typesafe arm). `TYPESAFE_API_KEY` was sourced from
`/home/montimage/workspace/anti-phishing-email-service/.env` into the gateway
process only; never printed or committed.

## Exact reproduction

```bash
# arm 1 — temp gateway, kev backend
S1_BACKEND=kev S1_PORT=8124 KEV_BASE_URL=http://localhost:8009/v1 \
    KEV_MODEL=kev-latest python3 configs/s1_gateway.py &
BENCH_BASE_URL=http://localhost:8124/v1 BENCH_MODEL=kev-latest \
    ./bench run --suite system1 --samples 2 --concurrency 1 \
    --label "kev-4b jaredpalmer kev.serve bf16 system1-v2" \
    --out results/2026-10-09-system1-v2-kev4b-vs-jev/kev-4b-kevserve-bf16-system1-v2.json

# arm 2 — same port after stopping the process above
S1_BACKEND=typesafe S1_PORT=8124 TYPESAFE_API_KEY=... \
    python3 configs/s1_gateway.py &
BENCH_BASE_URL=http://localhost:8124/v1 BENCH_MODEL=jev-latest \
    ./bench run --suite system1 --samples 2 --concurrency 1 \
    --label "typesafe jev-1.13.0 api.typesafe.ai system1-v2" \
    --out results/2026-10-09-system1-v2-kev4b-vs-jev/typesafe-jev-1-13-system1-v2.json
```

Settings both arms share: benchkit `s1_runner` (exact-match on the decision,
option-letter tolerant), `--samples 2` (800 scored generations per arm, 1,600
total), `--concurrency 1` for comparable per-question latency, `max_tokens
6000`, thinking OFF. **Thinking toggles are N/A**: both endpoints are
prefill-only typed decision services — the gateway ignores
`chat_template_kwargs`, `max_tokens` and temperature, so one arm each, not a
thinking A/B. `BENCH_CONCURRENCY` env does **not** reach `bench run` (argparse
default wins); the `--concurrency 1` flag is required — an earlier kev start at
concurrency 4 was aborted and its log kept as
`kev-4b-run-aborted-concurrency4.log`.

Smoke tests before each arm proved `/v1/models` returned the intended id
(`kev-latest`, `jev-latest`) and one real `policy_01` decision came back
correct through the full chat→`/v1/systemone` path.

Suite hash both runs: `0a6ba6f96eb5585c0e89a14cf655756026ee1413a08afaaee936908d55ef1b7e`
(identical dataset — valid head-to-head). Result JSONs carry `kind: s1`.

## Adapter policy (disclosed fallbacks, identical for both arms)

- Listed options → one `choice` question, `criteria = {option: null}`; answer
  is `answers.q.choice` verbatim.
- Open questions (20, all `records_*/q2`) → the documented
  "select instead of generate" pattern: `choice` over deduped state tokens,
  **capped at 64**. Measured coverage: `records_01/02/03/q2` answers
  (`REF-1-Q/2-Q/3-Q`) are **not** inside the candidate window, so those 3
  questions (6 of 800 generations) are unwinnable through this shim for *any*
  backend — equal handicap, counted as fails in both runs. `NONE` answers are
  inside the candidate set; misses on them are genuine model errors.
- `usage` maps backend-reported tokens; both backends report real counts.

## Family breakdown (accuracy, 80 generations per family per arm)

| Family | Jev 1.13.0 | Kev-4B bf16 |
|---|---|---|
| access | 72/80 90.0 % | 54/80 67.5 % |
| dependencies | 70/80 87.5 % | 46/80 57.5 % |
| events | 68/80 85.0 % | 46/80 57.5 % |
| evidence | 80/80 100 % | 64/80 80.0 % |
| inventory | 63/80 78.8 % | 42/80 52.5 % |
| money | 52/80 65.0 % | 50/80 62.5 % |
| policy | 63/80 78.8 % | 46/80 57.5 % |
| records | 47/80 58.8 % | 22/80 27.5 % |
| time | 48/80 60.0 % | 44/80 55.0 % |
| triage | 73/80 91.2 % | 64/80 80.0 % |

Question-type split: on the 380 optioned questions Jev 620/760 = 81.6 %,
Kev-4B 474/760 = 62.4 %; on the 20 open `records` questions Jev 16/40 = 40 %
(8/17 of the winnable ones per sample), Kev-4B 4/40 = 10 % (2/17).

Both models' weakest families are `money` (cents/shipping/credit arithmetic),
`time` (UTC offsets, inclusive/exclusive boundaries) and `records` (exact
joins + open answers). Kev-4B trails Jev in **every** family; the smallest gap
is `money` (62.5 vs 65.0) and `time` (55.0 vs 60.0). Failure overlap: 134
generations fail under both, 188 fail only under Kev-4B, 30 fail only under
Jev — Jev's unique misses are scattered single questions, not a distinct
capability hole. Zero generation failures / zero truncations in both runs;
every miss is a wrong decision, not a transport or contract error.

## Cost per question

| Arm | latency/q (TTFT≈total, prefill-only) | tokens/q in / out | wall for 800 |
|---|---|---|---|
| Jev | 0.236 s | 512 in / 70 out | 189 s |
| Kev-4B | 0.077 s | 225 in / 110 out | 62 s |

Kev-4B is ~3x faster per question and needs no WAN round-trip, API key or
per-call cost; Jev's latency is dominated by the hosted round-trip (TTFT≈full
latency on this prefill-only contract). Kev's open-question calls carry the
64-candidate expansion (~750 out-tokens), Jev's ~500 — both bounded.

## Correlation caveats

Sibling questions share each scenario's state, and many neighbouring fixtures
differ by a single fact across a decision boundary — the 800 scored responses
are **not** 800 independent cases. Consistent-with-design, most failures repeat
on both samples of a question (the suite's deterministic wrong-answer pull);
samples measure response variability, not new coverage. Wilson/Newcombe
intervals describe scored attempts; they overstate independent evidence, so
the family table — not just the headline — is where the decision rests.

## Saturation verdict

v2 is **not saturated**: the same two decision services that tied at 98.0 %
on `system1-legacy` separate cleanly here — 79.5 % vs 59.8 %, a +19.8 pp Jev
margin whose 95 % intervals are ~13 pp apart. The dataset discriminates;
per AGENTS.md guidance the close-race follow-up is more *distinct scenarios*,
not more samples. If Jev-class models approach ~95 % on v2, add failure-driven
families (money/time arithmetic slips are Jev's live frontier) rather than
parameter variants.

## Decision

**Keep TypeSafe Jev `jev-1.13.0` behind the standard s1 endpoint.** It wins on
every family, and the +19.8 pp margin is far outside noise. Kev-4B remains the
attractive *local* fallback — free, keyless, ~3x faster, already serving on
:8009 — but at 59.8 % it is not a drop-in replacement for Jev on v2 decision
quality; on legacy the same weights measured 95.9 %, which is exactly the
saturation this dataset was built to expose.
