# September 21 campaign — archive caveats

These are existing run artifacts archived during the 2026-09-30 repository
cleanup, not newly executed benchmarks. All nine JSON files are preserved unchanged.

## Exclude scoring-isolation failures from model rankings

- `incumbent-think-off.json`
- `incumbent-think-on.json`

Every generation in each file (56/56) failed scoring with
`unshare: unshare failed: Operation not permitted`. Their zero pass rates are
**harness/isolation failures, not model-quality measurements**. The legacy
`summary.errored: 0` counter does not account for these execution failures.
Do not include these two files in ranking reports; retain them as diagnostics.

The other seven files contain usable recorded outcomes, subject to the
limitations below.

## Interpretation limits

- Incumbent records use a serving alias, without immutable checkpoint or
  serving-configuration provenance. Agentic files measure benchkit's built-in
  tool loop, not an external harness.
- `container` is a run label; the artifacts do not establish the effective
  isolation settings. Do not infer a controlled isolation A/B from the label.
- Both container agentic runs record a 100% solve rate. This suite reached its
  discrimination ceiling for these runs; that is not proof of model perfection.
- Bonsai records alias `bonsai2-27b-pq2`; `CUDA` appears in its label, not as
  verified backend provenance. Its two execution timeouts remain recorded
  negative outcomes, not evidence of endpoint outages.
- No file records a suite fingerprint/schema-version stamp. Do not pool runs
  or assume suite equivalence with current benchmarks.
- Thinking flags record the requested mode, not proof of effective server settings.

No model replacement or serving change is justified by this archive review.
