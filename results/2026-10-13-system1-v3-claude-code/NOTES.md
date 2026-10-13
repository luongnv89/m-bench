# NOTES — system1-v3 via Claude Code: claude-haiku-5-5 at low effort (2026-10-13)

Harness: **claude-code** (Claude Code 2.1.296, OAuth). Model `claude-haiku-5-5`,
`--effort low`. 200 calls at `--samples 1`, sequential. Suite hash `65631df69caf…`,
the same as `../2026-10-10-system1-v3-200/`.

Driver `claude_s1.py` (this directory) is adapted from `pi_s1.py`. It uses the
same rendered prompt, s1 `SYSTEM` preamble (`--system-prompt`), scorer and
`summarize()`. Each call is an isolated `claude -p` in an empty temp dir. It runs
with no tools, MCP, skills, hooks or settings files, and with CLAUDE.md,
auto-memory and session persistence off. A smoke test confirmed that no
CLAUDE.md, hook or plugin context reached the model.

**Caveat:** `--bare` needs `ANTHROPIC_API_KEY`, and this run uses OAuth.
Without it, Claude Code's built-in preamble still goes out with each call: an
Agent SDK identity line, an env block (cwd, platform, date) and the account
e-mail line. None of it bears on the decision task. Latency includes about 1 s
of CLI start-up per call.

Reproduce:

```bash
python3 results/2026-10-13-system1-v3-claude-code/claude_s1.py claude-haiku-5-5 low \
  results/2026-10-13-system1-v3-claude-code/claude-haiku-5-5-effortlow-system1-v3.json
```

## Result

| Arm | Accuracy (95% CI) | Paraphrase-group acc. | s/q | out tok/q (thinking) | cost |
|---|---|---:|---:|---:|---:|
| claude-haiku-5-5 · effort low (claude-code) | **91.0 %** (86.2–94.2) | 85.0 | 2.31 | 37.2 (29.3) | $0.043 |

The margins against the v3 arms in `../2026-10-10-system1-v3-200/` (Newcombe 95 % CI) are:

| vs | margin (pp) | Verdict |
|---|---|---|
| gpt-6.1-sol medium (100.0) | −9.0 (−13.8 to −5.3) | real |
| gpt-6-luna max (99.5) | −8.5 (−13.3 to −4.5) | real |
| Qwen3.6 think-ON (97.0) | −6.0 (−11.0 to −1.3) | real |
| TypeSafe Jev (95.5) | −4.5 (−9.7 to +0.5) | **noise** |
| Qwen3.6 think-OFF (85.0) | +6.0 (−0.4 to +12.5) | **noise** |
| Kev-4B (71.0) | +20.0 (+12.5 to +27.4) | real |

Accuracy by family: access 95, billing 100, credentials 95, evidence 85,
injection 80, moderation 100, phishing 95, returns 95, **routing 70**,
triage 95. Each family has 20 items, so one item moves a cell 5 pp.

## Misses (18), all wrong options with no formatting failures

- `routing` 6 (01, 02, 09, 12, 18, 19): the wrong queue or the wrong human-needed flag. Routing is the weakest family.
- `injection` 4 (02, 10, 13, 15): two planted instructions not flagged, and two
  clean texts flagged as injection.
- `evidence` 3 (09, 11, 13): wrong supported/refuted/conflicting call.
- `phishing_16`: warns on a change notice. Jev and luna miss the same item.
- `returns_05`, `triage_02`, `access_08`, `credentials_04`: one each. `credentials_04` gives "expired" where the key is "revoked".

Only one effort level was run, by user request. Per the runbook, a second mode
(e.g. `--effort high`) is needed before this arm is compared as a product.
