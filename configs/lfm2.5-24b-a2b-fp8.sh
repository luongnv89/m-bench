#!/usr/bin/env bash
# LiquidAI LFM2.5-24B-A2B (official FP8 checkpoint) on vLLM, behind the stable
# alias montimage-dgx-spark. Runs attached (no -d) so systemd owns the lifecycle.
#
# Candidate to replace Qwen3.6-35B-A3B-NVFP4 (configs/qwen3.6-35b-a3b-nvfp4.sh);
# evaluated 2026-10-13, see results/2026-10-13-lfm2.5-vs-qwen3.6/.
#
# Hybrid MoE: 40 layers (30 short-conv + 10 GQA), 64 experts top-4, 2.45B active.
# Native to vLLM (Lfm2MoeForCausalLM) -- no --trust-remote-code. FP8 is
# compressed-tensors block-wise FP8, so the NVFP4-only --linear-backend
# flashinfer_b12x flag of the Qwen recipe is dropped. No MTP head in the
# checkpoint, so no speculative decoding.
#
# Always-thinking model: the chat template opens <think> on every assistant
# turn and ignores enable_thinking, so benchkit's think-OFF arm still reasons
# (just under the 6000-token default budget).
set -euo pipefail

MODEL_ID="LiquidAI/LFM2.5-24B-A2B-FP8"
IMAGE="ghcr.io/miaai-lab/mia-vllm-gb10-linear-b12x@sha256:19627342e1da2607f4db50745dca30e57d7dd0ebff06062f03fd69b43a252931"
NAME="vllm-qwen"
PORT="${QWEN_PORT:-8801}"
# Same 0.62 budget as the incumbent (~74 GB): weights ~24 GB, the rest KV.
UTIL="${QWEN_UTIL:-0.62}"
# Pin the KV/state cache exactly as the live incumbent launcher does
# (/home/montimage/llm-serving/start-qwen.sh): --gpu-memory-utilization alone
# sizes KV from free memory at profile time and once thrashed this host.
# NB: --kv-cache-memory-bytes, not the --kv-cache-memory vLLM's log suggests.
KV_CACHE_BYTES="${QWEN_KV_CACHE_BYTES:-34359738368}"
HF_HOME="${HF_HOME_DIR:-/home/montimage/llm-serving/hf-cache}"

mkdir -p "${HF_HOME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

# Flag notes (an inline `#` on a \-continued line swallows the backslash):
#   --reasoning-parser qwen3   Liquid's documented parser for the <think> block
#   --tool-call-parser lfm2    pythonic calls in <|tool_call_start|>[...]<|tool_call_end|>
#   --override-generation-config  model-card sampling (temp 0.1, top_k 50, rep 1.05)
#   text-only model: no --limit-mm-per-prompt needed, nothing can fetch media
exec docker run --rm \
  --name "${NAME}" \
  --user 1000:1000 \
  --network host \
  --shm-size=32g \
  --ulimit memlock=-1:-1 \
  --cap-add=IPC_LOCK \
  --ipc host \
  --gpus all \
  --entrypoint /usr/local/bin/vllm \
  -e VLLM_TARGET_DEVICE=cuda \
  -e CUTE_DSL_ARCH=sm_121a \
  -e HF_HOME=/home/1000/.cache/huggingface \
  -v "${HF_HOME}:/home/1000/.cache/huggingface" \
  "${IMAGE}" \
  serve "${MODEL_ID}" \
    --served-model-name montimage-dgx-spark "${MODEL_ID}" \
    --host 127.0.0.1 --port "${PORT}" \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization "${UTIL}" \
    --kv-cache-memory-bytes "${KV_CACHE_BYTES}" \
    --max-model-len 131072 \
    --max-num-seqs 12 \
    --max-num-batched-tokens 32768 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --async-scheduling \
    --kv-cache-dtype fp8 \
    --reasoning-parser qwen3 \
    --tool-call-parser lfm2 \
    --enable-auto-tool-choice \
    --override-generation-config '{"temperature":0.1,"top_k":50,"repetition_penalty":1.05}'
