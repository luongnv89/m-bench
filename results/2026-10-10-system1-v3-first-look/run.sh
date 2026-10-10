#!/usr/bin/env bash
# First v3 measurements: free local arms only, sequential, nothing restarted.
set -u
D=results/2026-10-10-system1-v3-first-look
BENCH_BASE_URL=http://localhost:8001/v1 BENCH_MODEL=montimage-dgx-spark \
  ./bench run --suite system1-v3 --samples 2 --concurrency 1 \
  --label "qwen3-6-35b-a3b-nvfp4 thinkoff system1-v3" \
  --out $D/qwen3-6-35b-a3b-nvfp4-thinkoff-system1-v3.json > $D/qwen-off-run.log 2>&1
BENCH_BASE_URL=http://localhost:8123/v1 BENCH_MODEL=kev-latest \
  ./bench run --suite system1-v3 --samples 2 --concurrency 1 \
  --label "kev-4b kev.serve bf16 via s1 gateway system1-v3" \
  --out $D/kev-4b-kevserve-bf16-system1-v3.json > $D/kev-run.log 2>&1
BENCH_BASE_URL=http://localhost:8001/v1 BENCH_MODEL=montimage-dgx-spark \
  ./bench run --suite system1-v3 --samples 2 --concurrency 1 --thinking --max-tokens 16000 \
  --label "qwen3-6-35b-a3b-nvfp4 thinkon system1-v3" \
  --out $D/qwen3-6-35b-a3b-nvfp4-thinkon-system1-v3.json > $D/qwen-on-run.log 2>&1
