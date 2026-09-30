## Method notes — TypeSafe Jev on `system1`

Jev is not a chat model: `POST https://api.typesafe.ai/v1/systemone` takes a
`state` and a map of typed `questions` (choice / noul / score) and returns
structured answers. The `system1` suite speaks OpenAI chat completions, so the
run went through `configs/typesafe-jev-shim.py` — a local shim on `:8123` that
parses each rendered s1 prompt back into (state, question, options) and issues
one upstream call per generation.

Translation used:

- **Options listed** → one `choice` question, `criteria = {option: null}`.
  Answer returned = `answers.q.choice` (the option text verbatim). Applies to
  48 of 49 questions.
- **No options** (`ref_code/q1`, the suite's only open question) → Jev has no
  free-text primitive, so the shim plays the documented
  "select instead of generate" pattern: a `choice` over candidate values =
  the deduped whitespace-split tokens of the state. Candidate coverage is a
  shim-side decision — stated here, not hidden. Jev picked `ZX-4821-Q`
  correctly on both samples.
- **Yes/no questions** → still `choice` (not `noul`): the suite asks "which of
  the listed options", so the uniform literal mapping was used rather than
  introducing a shim-side 0.5 threshold. The `noul` primitive is unmeasured.
- `usage.input_tokens/output_tokens` → `prompt_tokens`/`completion_tokens`.

Scope caveats: one TypeSafe call per question generation (98 calls for
samples=2) — the suite's per-question fan-out design, not TypeSafe's batched
questions-map style. Latency is *hosted-service* latency (WAN round-trip to
api.typesafe.ai), not local inference — unlike the incumbent's numbers.
Thinking mode is N/A: Jev has no deliberation block, so this is a single arm.
Upstream model resolved as `jev-1.13.0` (request alias `jev-latest`).
API key sourced from a neighbouring project's `.env`; never committed.
