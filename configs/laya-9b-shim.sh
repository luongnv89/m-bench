#!/usr/bin/env bash
# convaiinnovations/laya behind an OpenAI-compatible shim on 127.0.0.1:8804.
#
# laya is a 421M-param ModernBERT encoder, not a text generator: its native
# API is Router().predict(state, typed_questions). laya-shim.py (repo root)
# translates the suite's "State: / Question: / Options:" prompts into one
# typed `choice` call and streams the winning option's letter back as SSE —
# so the stock bench client drives it unchanged.
#
# Runs CPU-only by design: the GPU pool is nearly fully committed to the
# primary model, and ~0.4 s per decision on CPU is already far under the
# suite's per-task budget. CUDA_VISIBLE_DEVICES="" keeps it there.
#
# Requirements (once):
#   python3 -m venv /home/montimage/llm-serving/laya-venv
#   /home/montimage/llm-serving/laya-venv/bin/pip install laya aiohttp
#
# Serve it, then benchmark through the side port — the primary on :8001 is
# never touched:
#   bash configs/laya-9b-shim.sh &
#   BENCH_BASE_URL=http://127.0.0.1:8804/v1 BENCH_MODEL=laya \
#     ./bench run --suite system1 --samples 2 --label laya-s1-off
set -euo pipefail

VENV="${LAYA_VENV:-/home/montimage/llm-serving/laya-venv}"
PORT="${LAYA_PORT:-8804}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
exec "${VENV}/bin/python" "${HERE}/laya-shim.py" \
  --host 127.0.0.1 --port "${PORT}" --load-on-start
