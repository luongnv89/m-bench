# grep vs ripgrep vs ugrep — 2026-10-12

Wall-clock search speed of three grep-family tools on the DGX Spark. Coding agents
search code constantly, and harnesses choose different tools, so this measures that
one step. It is not an LLM benchmark. Published on the landing page's **Others** page
(`docs/others.html`).

## Environment

| | |
|---|---|
| Machine | NVIDIA DGX Spark · Cortex-X925 + A725, 20 threads · 119 GiB RAM · NVMe |
| OS | Ubuntu 24.04.4 LTS aarch64 · kernel 6.17.0-1032-nvidia · `LANG=en_US.utf8` |
| GNU grep | 3.11 (`/usr/bin/grep`, Ubuntu package `3.11-4build1`) |
| ripgrep | 14.1.0 (`/usr/bin/rg`, Ubuntu package `14.1.0-1`, `-simd-accel,+pcre2`) |
| ugrep | 7.8.5, built from source at tag `v7.8.5` (`f2cc252c`), gcc 13.3.0, `--without-pcre2` |
| ugrep (Claude Code) | 7.8.4, embedded in Claude Code 2.1.296, run as `exec -a ugrep <claude binary>` |

## Corpus

- **tree** — shallow clone of `torvalds/linux` at `d6d3455d8751854e0d1820f14184682e23ac4475`
  (2026-10-11): 96,080 tracked files, 1.8 GB worktree. This is the corpus ripgrep's own benchmarks use.
- **file** — every `*.c` and `*.h` in that tree concatenated into one file: 1,453,600,924 bytes,
  37,689,961 lines.

## Method

`run.py` times each command with one warmup run and then takes the median of 7 runs. The page
cache is warm, and the corpus fits in RAM.

- Output is piped to `wc -l`, never to `/dev/null`. GNU grep detects `/dev/null` and stops at
  the first match.
- grep and ugrep run with `-rnI --exclude-dir=.git` to match ripgrep's defaults: skip `.git`,
  skip binary files. The fresh clone has no gitignored files, so all three tools search the
  same files.
- ripgrep's `-E` flag means `--encoding`, not extended regex, so `run.py` removes it from ripgrep's commands.
- `rg -j1` and `ugrep -J1` limit each tool to one thread. This separates the search engine from
  parallel directory walking. On a single file both tools already use one thread.
- The match count is recorded for each tool. All tools returned identical counts in every row.

```bash
python3 -I run.py <corpus-dir> <path/to/ugrep> <path/to/claude-binary> [case-filter]
```

## Results

`results.tsv` holds median seconds per case. The `run` column records where a row came from:
`full` rows are from one full run. `rerun` rows are from a filtered rerun of that case, done after
the first run's ripgrep regex commands failed on `-E`; every tool in a `rerun` row was re-measured in that pass. An earlier
grep/ripgrep-only run gave ripgrep numbers within 6% of these.

- **Searching the tree:** ripgrep is 11–20× faster than GNU grep, and ugrep is 8–16× faster.
  ripgrep leads ugrep by about 1.35×.
- **Single thread:** ugrep matches or slightly beats ripgrep (0.59–0.73 s vs 0.62–0.72 s).
  ripgrep's lead in the tree comes from its parallel directory walk.
- **One large file:** ripgrep is 4.8–7.0× faster than GNU grep, and ugrep is 3.1–6.4× faster.
  ripgrep is 1.1–1.8× faster than ugrep.
- **Embedded vs standalone ugrep:** the copy embedded in Claude Code runs within noise of the
  standalone build. Startup cost is 4 ms vs 3 ms.
