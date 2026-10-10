# NOTES — system1-v3 at 200 calls per arm (2026-10-10)

`system1-v3` is the 200-call design: 200 scenarios, one combined
decision-and-reason question each, `--samples 1`. Four arms ran sequentially
at `--concurrency 1`. TypeSafe Jev ran through a private s1 gateway on :8124
(`S1_BACKEND=typesafe`, key sourced from the anti-phishing service's `.env`
into the gateway process only, never printed). The gateway was stopped after
the run. The three free local arms are Qwen3.6-35B-A3B-NVFP4 on :8001 with thinking
off and on (`--max-tokens 16000`), and Kev-4B behind the shared s1 gateway on
:8123. Nothing was restarted or reconfigured. Reproduce with `run.sh`. Suite hash
`65631df69caf…` (full value in each JSON). It supersedes the 400-question draft
in `../2026-10-10-system1-v3-first-look/`.

Two frontier OpenAI models then ran through the pi CLI with `pi_s1.py` (this
directory, adapted from the v2 driver to take `--suite`, default 1 sample,
and record `scenario_metrics`): gpt-6-luna at `max` thinking and gpt-6.1-sol at
`medium` thinking. Each call is an isolated `pi -p` with no session, tools, MCP
or extensions. The prompt, system preamble and scorer are the same as for every
other arm. Latency includes about 1 s of pi process start-up per call. The two
ran in parallel with each other, each sequential.

Mercury Decide is not on the v3 roster, by user decision.

Jev reproduction:

```bash
S1_BACKEND=typesafe S1_PORT=8124 TYPESAFE_API_KEY=... python3 configs/s1_gateway.py &
BENCH_BASE_URL=http://localhost:8124/v1 BENCH_MODEL=jev-latest \
  ./bench run --suite system1-v3 --samples 1 --concurrency 1 \
  --label "typesafe jev-1.13.0 api.typesafe.ai system1-v3" \
  --out results/2026-10-10-system1-v3-200/typesafe-jev-1-13-system1-v3.json
```

A smoke test of `returns_01` through the full chat → `/v1/systemone` path
returned the correct answer from `jev-1.13.0` before the run.

## Results (200 scored calls per arm)

| Arm | Accuracy (95% CI) | Paraphrase-group acc. | s/q | out tok/q |
|---|---|---:|---:|---:|
| gpt-6.1-sol · think-medium (pi) | **100.0 %** (98.1–100) | 100 | 3.24 | 6.2 |
| gpt-6-luna · think-max (pi) | **99.5 %** (97.2–99.9) | 100 | 4.91 | 76.2 |
| Qwen3.6 think-ON | **97.0 %** (93.6–98.6) | 93.3 | 9.61 | 796.6 |
| TypeSafe Jev 1.13.0 | **95.5 %** (91.7–97.6) | 93.3 | 0.22 | 84.8 |
| Qwen3.6 think-OFF | **85.0 %** (79.4–89.3) | 75.0 | 0.23 | 7.0 |
| Kev-4B (s1 gateway) | **71.0 %** (64.4–76.8) | 68.3 | 0.15 | 136.7 |

On v2 (800 calls) the same arms scored 98.6 / 79.5 (Jev) / 61.8 / 59.8.

Jev margins (Newcombe 95 % CI): vs gpt-6.1-sol −4.5 pp (−8.3 to −1.7) and vs
gpt-6-luna −4.0 pp (−7.9 to −0.9), both real but small. vs Qwen think-ON −1.5 pp
(−5.7 to +2.5), which is **noise**. vs Qwen think-OFF +10.5 pp (+4.8 to +16.5). vs Kev-4B +24.5 pp
(+17.5 to +31.5).

| Family | Kev-4B | Qwen-OFF | Jev | Qwen-ON | luna max | sol medium |
|---|---:|---:|---:|---:|---:|---:|
| access | 85 | 75 | 90 | 85 | 100 | 100 |
| billing | 80 | 90 | 90 | 95 | 100 | 100 |
| credentials | 85 | 85 | 100 | 100 | 100 | 100 |
| evidence | 65 | 90 | 95 | 100 | 100 | 100 |
| injection | 30 | 90 | 100 | 100 | 100 | 100 |
| moderation | 100 | 100 | 100 | 95 | 100 | 100 |
| phishing | 75 | 75 | 95 | 95 | 95 | 100 |
| returns | 60 | 70 | 85 | 100 | 100 | 100 |
| routing | 55 | 75 | 100 | 100 | 100 | 100 |
| triage | 75 | 100 | 100 | 100 | 100 | 100 |

Each family has 20 items, so a family cell moves 5 pp per item. Read family
gaps under 15 pp as indicative only.

## Reading

- **v3 is saturated at the frontier.** gpt-6.1-sol at medium thinking answers
  all 200 correctly. gpt-6-luna at max misses one, `phishing_16`, the same
  change-notice item Jev misses. Both keep every paraphrase pair. On v2 the gap
  between Jev and this tier was about 20 pp; on v3 it is about 4 pp, small but
  outside noise. Reasoning still helps, mostly on the threshold and
  grant-precedence cases listed below. v3 cannot rank frontier models against
  each other; it ranks System One candidates.
- **Within the System One class, Jev leads:** +10.5 pp over Qwen think-OFF and
  +24.5 pp over Kev-4B, at 0.22 s/q.

- **Jev and thinking-on Qwen are statistically tied on v3** (95.5 vs 97.0, the
  margin interval spans zero), while Jev answers about 44× faster (0.22 vs
  9.6 s/q) with about a tenth of the output tokens. On v2 the same pair was
  79.5 vs 98.6. That 19-point gap came from the computation v3 removes.
- **Jev's 9 misses:**
  - `returns_03/04/16`: refund at 45 days and inspection at 400 days, missing
    the 30-day and 365-day limits.
  - `access_15/16`: lets a grant upgrade a viewer, the same error thinking-on
    made.
  - `billing_11/12`: an open chargeback marked settled, in both renderings
    (thinking-on missed `billing_11` too).
  - `evidence_19`: "didn't see by whom" read as denying who signed.
  - `phishing_16`: a change notice treated as a change request.
  - Six of the nine are three cases missed in both renderings. The threshold
    misses are the residual System Two tilt.
- **The think-ON / think-OFF gap is 12 pp, down from 36.8 pp on v2**, with
  disjoint intervals. Reasoning still helps on decision work. It no longer wins
  by calculating.
- **The combined answers are stricter than the 400-question draft.** Kev-4B
  falls from 80.5 to 71.0, mostly in `injection` (30 %). It almost never flags
  planted instructions, and the combined answer now requires that flag.
- **Paraphrase stability** separates the arms beyond accuracy: Kev-4B 68, Qwen-OFF 75,
  Jev 93, Qwen-ON 93, luna 100 and sol 100 %.
- **Saturated families:** `moderation` (every arm 95–100) and `triage` (every
  arm but Kev-4B at 100).
  They need harder cases before v3 replaces v2.
- **Thinking-on's 6 misses:** three in `access`, where it allowed a pending
  grant, a viewer with a grant, or an admin of another project; one chargeback
  marked settled; and one lookalike domain read as authentic. None point to a
  key problem. `moderation_06` is a formatting miss: the reply `b) keep` has
  the right letter but cuts the option text, and the shared scorer only
  accepts a bare letter or the letter with the full option text. The scorer
  was left unchanged. This is the only such reply across all six arms (1,200 calls).
- **Cost of the frontier arms (pi-reported):** luna $0.011 and sol $0.14 for
  200 calls each.
