# September 18 campaign — archive caveats

These are existing run artifacts archived during the 2026-09-30 repository
cleanup, not newly executed benchmarks. All ten JSON files are preserved unchanged.

## Exclude scoring-isolation failures from model rankings

- `incumbent-qwen3-6-35b-a3b-nvfp4-think-off.json`
- `incumbent-qwen3-6-35b-a3b-nvfp4-think-on.json`

Every generation in each file (56/56) failed scoring with
`unshare: unshare failed: Operation not permitted`. Their zero pass rates are
**harness/isolation failures, not model-quality measurements**. The legacy
`summary.errored: 0` counter does not account for these execution failures.
Do not include these two files in ranking reports; retain them as diagnostics.

The `think-off-valid` and `think-on-valid` files are separate recorded runs,
not edits to those failed artifacts. The other eight files contain usable
recorded outcomes, subject to the limitations below.

## Interpretation limits

- The incumbent records `montimage-dgx-spark`, a serving alias rather than an
  immutable checkpoint identity. `serving_config` and `harness` are empty.
  Agentic files measure benchkit's built-in tool loop, not an external harness.
- Bonsai one-shot records name a GGUF path but do not record a weight hash.
- No file records a suite fingerprint/schema-version stamp. Do not pool runs
  or assume suite equivalence with current benchmarks.
- Thinking flags record the requested mode, not proof of effective server settings.
- Bonsai thinking-ON records 21/56 truncated generations; agentic-ON records
  four stalled trajectories. These are recorded limitations, not established
  endpoint failures.

No model replacement or serving change is justified by this archive review.
