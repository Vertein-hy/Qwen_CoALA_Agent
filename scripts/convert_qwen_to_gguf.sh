#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/convert_qwen_to_gguf.sh Qwen/Qwen3.5-9B-Instruct Q4_K_M
#
# This script:
# 1) downloads HF safetensors model
# 2) converts to f16 gguf
# 3) quantizes to target type

MODEL_ID="${1:-Qwen/Qwen3.5-9B-Instruct}"
QUANT="${2:-Q4_K_M}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_DIR="${ROOT_DIR}/models/hf"
GGUF_DIR="${ROOT_DIR}/models/gguf"
LLAMA_CPP_DIR="${ROOT_DIR}/third_party/llama.cpp"

mkdir -p "${HF_DIR}" "${GGUF_DIR}" "${ROOT_DIR}/third_party"

if [[ ! -d "${LLAMA_CPP_DIR}" ]]; then
  git clone https://github.com/ggml-org/llama.cpp.git "${LLAMA_CPP_DIR}"
fi

cmake -S "${LLAMA_CPP_DIR}" -B "${LLAMA_CPP_DIR}/build" -DGGML_METAL=ON
cmake --build "${LLAMA_CPP_DIR}/build" -j

HF_LOCAL_PATH="${HF_DIR}/$(basename "${MODEL_ID}")"
huggingface-cli download "${MODEL_ID}" --local-dir "${HF_LOCAL_PATH}"

F16_OUT="${GGUF_DIR}/$(basename "${MODEL_ID}")-f16.gguf"
python3 "${LLAMA_CPP_DIR}/convert_hf_to_gguf.py" "${HF_LOCAL_PATH}" --outfile "${F16_OUT}" --outtype f16

QUANT_OUT="${GGUF_DIR}/$(basename "${MODEL_ID}")-${QUANT}.gguf"
"${LLAMA_CPP_DIR}/build/bin/llama-quantize" "${F16_OUT}" "${QUANT_OUT}" "${QUANT}"

echo "Done: ${QUANT_OUT}"
