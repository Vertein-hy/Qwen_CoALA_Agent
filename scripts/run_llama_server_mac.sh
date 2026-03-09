#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/run_llama_server_mac.sh models/gguf/Qwen3.5-9B-Instruct-Q4_K_M.gguf

MODEL_PATH="${1:-}"
if [[ -z "${MODEL_PATH}" ]]; then
  echo "Missing model path."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA_CPP_DIR="${ROOT_DIR}/third_party/llama.cpp"

if [[ ! -x "${LLAMA_CPP_DIR}/build/bin/llama-server" ]]; then
  echo "llama-server not found. Build llama.cpp first."
  exit 1
fi

"${LLAMA_CPP_DIR}/build/bin/llama-server" \
  -m "${MODEL_PATH}" \
  --host 127.0.0.1 \
  --port 8000 \
  --ctx-size 8192 \
  --n-gpu-layers 99 \
  --alias qwen-local-gguf
