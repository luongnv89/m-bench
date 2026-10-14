# NOTES — system1-v3 via Claude Code: claude-sonnet-5-5 at low and high effort (2026-10-14)

Harness: **claude-code** (Claude Code 2.1.296, OAuth). Model `claude-sonnet-5-5`,
`--effort low` and `--effort high`. 200 calls per arm at `--samples 1`. The two
arms ran in parallel, each one sequential. Suite hash `65631df69caf…`.

The driver is `../2026-10-13-system1-v3-claude-code/claude_s1.py`, unchanged.
Isolation and its caveat are documented there and in that directory's NOTES:
no tools, MCP, skills, hooks, settings files, CLAUDE.md or auto-memory. Claude
Code's built-in preamble remains because `--bare` needs an API key. Latency
includes about 1 s of CLI start-up per call.

Reproduce:

```bash
D=results/2026-10-14-system1-v3-claude-code-sonnet
DRV=results/2026-10-13-system1-v3-claude-code/claude_s1.py
python3 $DRV claude-sonnet-5-5 low  $D/claude-sonnet-5-5-effortlow-system1-v3.json
python3 $DRV claude-sonnet-5-5 high $D/claude-sonnet-5-5-efforthigh-system1-v3.json
```

## Results

| Arm | Accuracy (95% CI) | Paraphrase-group acc. | s/q | out tok/q | thinking used | cost |
|---|---|---:|---:|---:|---:|---:|
| claude-sonnet-5-5 · effort low (claude-code) | **100.0 %** (98.1–100) | 100 | 3.88 | 8.6 | 1 / 200 calls | $0.81 |
| claude-sonnet-5-5 · effort high (claude-code) | **100.0 %** (98.1–100) | 100 | 4.34 | 10.9 | 5 / 200 calls | $0.34 |

- **Both arms saturate v3.** They answer 200/200 with every paraphrase pair
  kept and every family at 100. That ties gpt-6.1-sol at medium thinking.
  v3 cannot rank this tier or tell the two effort levels apart.
- **Sonnet hardly uses thinking on these prompts.** It thought on 1 call at
  low effort and 5 at high. Answers are a bare letter or the option text, at
  9–11 output tokens on average.
- **Margins:** +4.5 pp over Haiku 5.5 high (+1.7 to +8.3, real), +9.0 pp over
  Haiku 5.5 low (+5.3 to +13.8, real), and +4.5 pp over Jev (+1.7 to +8.3, real).
  Sonnet also gets `phishing_16` right, the item that Jev, gpt-6-luna and Haiku
  at low effort miss.
- **Cost** comes from Claude Code's `total_cost_usd`. It depends on prompt
  caching: the two arms ran at the same time with the same system prompt, so
  cache creation and cache reads may have split unevenly between them. The
  per-call records do not separate the two, so the cause is unverified. Do not
  read the cost gap as an effort effect.
