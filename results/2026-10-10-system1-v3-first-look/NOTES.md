# NOTES — first look at system1-v3 (2026-10-10)

> **Superseded draft.** These runs used the 400-question draft of v3 (two
> questions per scenario, `--samples 2`, 800 calls per arm; a different
> `suite_hash`). The 200-call version is measured in
> `../2026-10-10-system1-v3-200/`.

The first measurements of the candidate v3 suite (`system1-v3`, 200 scenarios /
400 optioned questions). They are free local arms only: Qwen3.6-35B-A3B-NVFP4
on :8001 with thinking off and on, and Kev-4B behind the shared s1 gateway on
:8123 (kev backend, as already deployed). Every arm used `--samples 2`
(800 generations) and `--concurrency 1`. Nothing was restarted or reconfigured.
**Jev is not measured on this draft.** It was measured on the 200-call
version. Mercury is not on the v3 roster. Reproduce with `run.sh`.

Suite hash for all three runs: the `suite_hash` in each JSON (identical).

## Key verification before the runs

An independent blind annotator answered all 400 questions from the rendered
states alone. It agreed with **400/400** keys. It flagged 15 wording issues
where a second reading was defensible. All 15 were reworded before these runs
with no key changes: personal-account senders, change notices vs requests,
"already paid" vs dispute, "not run" vs "passed", implied and group threats,
conditional legal threats, time-anchored denials and grant dates.

## Results

| Arm | Accuracy (95% CI) | Scenario acc. | Paraphrase-group acc. | s/q | out tok/q |
|---|---|---:|---:|---:|---:|
| Qwen3.6 think-ON | **98.6 %** (97.6–99.2) | 97.8 | 95.8 | 8.40 | 702.7 |
| Qwen3.6 think-OFF | **88.2 %** (85.8–90.3) | 82.2 | 68.3 | 0.21 | 4.2 |
| Kev-4B (s1 gateway) | **80.5 %** (77.6–83.1) | 71.5 | 68.3 | 0.08 | 75.1 |

Same arms on v2: think-ON 98.6, think-OFF 61.8, Kev-4B 59.8.

| Family | Kev-4B | Qwen-OFF | Qwen-ON |
|---|---:|---:|---:|
| access | 87.5 | 66.2 | 92.5 |
| billing | 90.0 | 93.8 | 98.8 |
| credentials | 92.5 | 91.2 | 97.5 |
| evidence | 70.0 | 88.8 | 100 |
| injection | 75.0 | 97.5 | 100 |
| moderation | 100 | 100 | 100 |
| phishing | 67.5 | 91.2 | 97.5 |
| returns | 55.0 | 70.0 | 100 |
| routing | 80.0 | 83.8 | 100 |
| triage | 87.5 | 100 | 100 |

## What this shows

- **Most of the compute bias is gone.** The thinking-on vs thinking-off gap on
  the same weights fell from 36.8 pp (v2) to 10.4 pp (v3). Single-pass arms
  rose by about 20–27 pp, while thinking-on stayed at 98.6 %.
- **Reasoning still leads, and the remaining gap is concentrated.** Qwen-OFF's
  misses are mostly in `access` and `returns`. They come from ordered
  first-match policies with conjunctive conditions where the answer is the
  fall-through `DEFAULT`/`R6`, so the model must notice that one condition of
  the tempting rule fails: wrong project, viewer with a grant, 45 > 30 days,
  400 > 365 days. That is legitimate policy compliance, but it is also where
  step-by-step checking pays. Whether to keep it at this weight is a design
  decision.
- **The families now fail for decision-shaped reasons.** Kev-4B's misses are
  lookalike and mismatched domains (`phishing`), detecting planted instructions
  (`injection` q2 is almost always "no"), self-corrections and hearsay
  (`evidence`), and confirmed vs claimed damage (`returns`). None of them come
  from arithmetic.
- **Paraphrase pairs separate arms that per-question accuracy does not.** Both
  fast arms hold only 68.3 % of paraphrase pairs fully correct, against 95.8 %
  for thinking-on. The decision changes when the same case is reworded.
- **Saturated families.** `moderation` is 100 % for all three arms, and `triage`
  is 100 % for both Qwen modes. They do not separate these arms and need harder
  cases before v3 is promoted, unless Jev misses them.
- Thinking-on's 11 misses are `access_15/16`: it lets a grant upgrade a viewer,
  which the policy explicitly forbids. The rest are two truncations at 16k
  tokens and four scattered single misses. No key problems were found.

## Not done

- Jev was not run on this draft; see `../2026-10-10-system1-v3-200/`.
- No landing-page, ledger or `system1` default change. v3 stays a candidate.
