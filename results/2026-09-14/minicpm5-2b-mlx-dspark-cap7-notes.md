## Local setup

- Machine: Apple M1 Max, 32-core GPU, 32 GB unified memory.
- Server: mlx-dspark 0.19.0, MLX 0.32.2.
- Target: `mlx-community/MiniCPM5-2B-bf16`.
- Drafter: `openbmb/MiniCPM5-2B-DSpark`.
- Serving mode: DSpark with fixed draft cap 7.
- Benchmark path: benchkit built-in agentic tool loop, `agentic-hard`, 2 samples per task.

## Interpretation

Thinking ON improved pass@1 from 75.0% to 81.2%, but the 6.2-point difference is below this repository's approximate 8-point noise threshold at two samples. It also increased mean output from 1,764 to 6,207 tokens and wall time from 834 to 2,548 seconds. Agent score was nearly unchanged (36.6 vs 37.7), so the extra reasoning cost did not produce a decisive practical gain.

Both modes were inefficient relative to oracle paths: 14.8–15.8 calls versus 5.9 par, with stalled or turn-limit runs. Thinking OFF is therefore the better default for agentic use on this machine. Thinking ON should be reserved for difficult retries rather than enabled globally.
