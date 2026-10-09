# Method notes — Nimble arm added to the system1-v2 campaign

Third arm of the same campaign (`results/2026-10-09-system1-v2-kev4b-vs-jev`),
same transport and settings as the Jev/Kev arms: this worker's temporary
`configs/s1_gateway.py` on `http://localhost:8124/v1` (server PID 1441177),
`S1_BACKEND=nimble` → `NIMBLE_BASE_URL=http://localhost:11434/v1`,
`NIMBLE_MODEL=nimble`. Upstream is the already-running
`ollama-nimble.service` (Ollama 0.35) serving `nimble:latest` =
`Bespoke-Nimble-9B-merged-current-Q8_0.gguf` (9.0B, Q8_0, qwen35 family,
~9.5 GiB). Queried, never restarted or reconfigured. `system1` v2,
`--samples 2 --concurrency 1`, `BENCH_MODEL=nimble`, thinking N/A
(prefill-only typed decision endpoint), `max_tokens 6000` ignored by the
gateway. Same `suite_hash` `0a6ba6f9…` as the other two arms.

## Transport failure — must read before comparing

**40 of 800 Nimble generations are transport failures, not wrong decisions.**
Every open question (`records_*/q2`, 20 questions × 2 samples) returned a
gateway `502` wrapping an Ollama `400`:

```
question "q": criteria must contain 2–26 candidates
```

The gateway's documented open-question fallback builds a `choice` over up to
64 deduped state tokens; Ollama's `/v1/systemone` caps `criteria` at 26. All
20 open-question answers sit at candidate positions 48–61 (`REF-4/5-Q`,
`NONE`) or are absent entirely (`REF-1/2/3-Q`), so **no 26-candidate list can
ever cover a v2 open-question answer** — the questions are unwinnable for
Nimble through this transport, harder than the Jev/Kev handicap (17 of 20
winnable for them). Direct probes against Ollama confirmed: a 26-candidate
`choice` request succeeds (so the cap is the sole cause), and the `noul`
type is supported but returns an epistemic probability, not a free-text
answer — there is no primitive on this contract that answers v2's open
questions for Nimble.

Scored interpretations, in order of comparability:

| Subset | Nimble | Jev | Kev-4B |
|---|---|---|---|
| 380 optioned questions (760 gens) — the level field | **71.6 %** (544/760) | **81.6 %** (620/760) | **62.4 %** (474/760) |
| all 400 questions as scored (n=800) | 68.0 % (CI 64.7–71.1) | 79.5 % (CI 76.6–82.2) | 59.8 % (CI 56.3–63.1) |

On `records_*` Nimble's scored 8/40 is q1-only (q2 all errored): its 20 % on
the compound-join optioned questions is actually the weakest of the three
there (Jev q1 31/40 = 77.5 %, Kev q1 18/40 = 45 %).

## Family breakdown — scored generations only (errors excluded)

| Family | Jev | Nimble | Kev-4B |
|---|---|---|---|
| access | 90.0 % | 77.5 % | 67.5 % |
| dependencies | 87.5 % | 62.5 % | 57.5 % |
| events | 85.0 % | 77.5 % | 57.5 % |
| evidence | 100 % | 92.5 % | 80.0 % |
| inventory | 78.8 % | 72.5 % | 52.5 % |
| money | 65.0 % | 62.5 % | 62.5 % |
| policy | 78.8 % | **85.0 %** | 57.5 % |
| records | 58.8 % | 20.0 % (q1 only) | 27.5 % |
| time | 60.0 % | 60.0 % | 55.0 % |
| triage | 91.2 % | 80.0 % | 80.0 % |

Nimble beats Kev-4B in eight of ten families (ties `money`, `triage`) and
even edges Jev on `policy` (85.0 vs 78.8) — but trails Jev ~10 pp overall on
the optioned subset. Its 98 % parity with Jev on `system1-legacy` does **not**
hold on v2; Jev separates from both local models.

## Cost per question

| Arm | latency/q | tokens/q | wall (800) |
|---|---|---|---|
| Nimble | ~0.14 s | 367 in / 1 out | 114 s |
| Jev | 0.236 s | 512 in / 70 out | 189 s |
| Kev-4B | 0.077 s | 225 in / 110 out | 62 s |

Nimble emits a single output token per decision (the option text as one
token) — cheapest output of the three; latency is local-serving plus the
in-process gateway hop.

## Decision impact

None: the v2 ranking is Jev > Nimble > Kev-4B on the comparable subset, and
the endpoint decision from the two-arm report stands. Nimble remains the
strongest *local* decision backend (clearly ahead of Kev-4B), but it is not
the drop-in Jev replacement the legacy suite suggested — and its open-question
coverage is zero through the standard gateway today. If local serving is
required and Jev's WAN round-trip is unacceptable, Nimble is the pick among
measured local options; fixing the open-question gap needs a gateway-side
policy (e.g. candidate cap-aware selection or a different fallback for
`nimble`), not a model change — flagged here as adapter work, not measured.
