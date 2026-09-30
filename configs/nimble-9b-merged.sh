#!/usr/bin/env bash
# FALLBACK recipe: serve a merged Nimble checkpoint as "nimble-9b" on :8803.
#
# Use this only when configs/nimble-9b-lora.sh cannot start — e.g. the pinned
# vLLM build lacks --enable-lora support or the Qwen3.5 architecture. The
# merged checkpoint is built once, outside docker, with peft:
#
#   pip install peft transformers
#   python3 - <<'PY'
#   import torch
#   from peft import PeftModel
#   from transformers import AutoModelForCausalLM, AutoTokenizer
#   base = AutoModelForCausalLM.from_pretrained(
#       "Qwen/Qwen3.5-9B", dtype=torch.bfloat16)
#   merged = PeftModel.from_pretrained(
#       base, "bespokelabs/Bespoke-Nimble-9B").merge_and_unload()
#   merged.save_pretrained("/home/montimage/llm-serving/models/nimble-9b-merged")
#   AutoTokenizer.from_pretrained(
#       "bespokelabs/Bespoke-Nimble-9B").save_pretrained(
#       "/home/montimage/llm-serving/models/nimble-9b-merged")
#   PY
#
# Then this script serves that directory with the same flags as the LoRA
# recipe, minus the LoRA flags. Same port, alias, memory budget and context
# cap, so results are comparable across the two serving paths.
set -euo pipefail

MODEL_ID="${NIMBLE_MERGED_DIR:-/home/montimage/llm-serving/models/nimble-9b-merged}"
IMAGE="ghcr.io/miaai-lab/mia-vllm-gb10-linear-b12x@sha256:19627342e1da2607f4db50745dca30e57d7dd0ebff06062f03fd69b43a252931"
NAME="vllm-nimble"
PORT="${NIMBLE_PORT:-8803}"
UTIL="${NIMBLE_UTIL:-0.19}"
MAXLEN="${NIMBLE_MAXLEN:-8192}"
HF_HOME="${HF_HOME_DIR:-/home/montimage/llm-serving/hf-cache}"

if [ ! -d "${MODEL_ID}" ]; then
  echo "merged checkpoint not found at ${MODEL_ID}" >&2
  echo "build it first with the peft merge_and_unload snippet in this file's header" >&2
  exit 1
fi

mkdir -p "${HF_HOME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

# MODEL_ID is a host path here, so it is mounted read-only into the container
# at the same location and served from there.
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
  -v "${MODEL_ID}:${MODEL_ID}:ro" \
  "${IMAGE}" \
  serve "${MODEL_ID}" \
    --served-model-name nimble-9b \
    --host 127.0.0.1 --port "${PORT}" \
    --tensor-parallel-size 1 \
    --trust-remote-code \
    --gpu-memory-utilization "${UTIL}" \
    --attention-backend flashinfer \
    --max-model-len "${MAXLEN}" \
    --max-num-seqs 8 \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --kv-cache-dtype fp8
