#!/usr/bin/env bash
# bespokelabs/Bespoke-Nimble-9B on vLLM, on 127.0.0.1:8803.
#
# Nimble is a ~165 MiB LoRA adapter, not a standalone checkpoint: vLLM loads
# the Qwen/Qwen3.5-9B base (~18 GB bf16, served under its own repo id) and
# hot-loads the adapter as the "nimble" LoRA module — the adapter is what
# answers to BENCH_MODEL=nimble; there is deliberately no "nimble-9b" alias on
# the base, so that name can never silently measure unadapted weights.
# The adapter's published contract caps context at 8192 tokens, so
# --max-model-len is pinned there.
#
# Secondary side-port backend (same pattern as configs/gemma4-12b-w4a16.sh):
# it shares the GPU with the primary model, so UTIL stays small. 0.19 of the
# 119 GB pool is ~22.6 GB: ~18 GB weights + ~4 GB KV. If it does not fit
# alongside the incumbent, run it with the primary stopped, or fall back to
# configs/nimble-9b-merged.sh.
set -euo pipefail

MODEL_ID="Qwen/Qwen3.5-9B"
LORA="bespokelabs/Bespoke-Nimble-9B"
IMAGE="ghcr.io/miaai-lab/mia-vllm-gb10-linear-b12x@sha256:19627342e1da2607f4db50745dca30e57d7dd0ebff06062f03fd69b43a252931"
NAME="vllm-nimble"
PORT="${NIMBLE_PORT:-8803}"
UTIL="${NIMBLE_UTIL:-0.19}"
MAXLEN="${NIMBLE_MAXLEN:-8192}"
HF_HOME="${HF_HOME_DIR:-/home/montimage/llm-serving/hf-cache}"

mkdir -p "${HF_HOME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

# Keep every comment above this line: a `#` on a \-continued line below
# swallows the backslash and truncates the docker command (issue #74).
# The adapter is LoRA rank 16, which is also vLLM's default --max-lora-rank;
# it is pinned explicitly so a future default change cannot silently refuse
# the module.
exec docker run --rm \
  --name "${NAME}" \
  --user root \
  --network host \
  --shm-size=8g \
  --ulimit memlock=-1:-1 \
  --cap-add=IPC_LOCK \
  --ipc host \
  --gpus all \
  --entrypoint /usr/local/bin/vllm \
  -e VLLM_TARGET_DEVICE=cuda \
  -e CUTE_DSL_ARCH=sm_121a \
  -e HF_HOME=/root/.cache/huggingface \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -v "${HF_HOME}:/root/.cache/huggingface" \
  "${IMAGE}" \
  serve "${MODEL_ID}" \
    --host 127.0.0.1 --port "${PORT}" \
    --tensor-parallel-size 1 \
    --trust-remote-code \
    --gpu-memory-utilization "${UTIL}" \
    --attention-backend flashinfer \
    --max-model-len "${MAXLEN}" \
    --max-num-seqs 8 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --enable-lora \
    --max-lora-rank 16 \
    --lora-modules "nimble=${LORA}" \
    --kv-cache-dtype fp8
