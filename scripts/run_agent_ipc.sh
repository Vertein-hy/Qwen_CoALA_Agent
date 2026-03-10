#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEALTH_URL="${COALA_IPC_HEALTH_URL:-http://127.0.0.1:18081/health}"
MODELS_URL="${COALA_IPC_MODELS_URL:-http://127.0.0.1:18081/v1/models}"

export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}"
export no_proxy="${no_proxy:-localhost,127.0.0.1}"

export COALA_LOCAL_PROVIDER="${COALA_LOCAL_PROVIDER:-openai_compat}"
export COALA_LOCAL_MODEL="${COALA_LOCAL_MODEL:-Qwen3.5-9B-Q4_K_M.gguf}"
export COALA_LOCAL_API_BASE="${COALA_LOCAL_API_BASE:-http://127.0.0.1:18081/v1}"
export COALA_LOCAL_REQUIRE_API_KEY="${COALA_LOCAL_REQUIRE_API_KEY:-false}"
export COALA_LOCAL_API_KEY="${COALA_LOCAL_API_KEY:-local-key}"
export COALA_LOCAL_SUPPORTS_TOP_K="${COALA_LOCAL_SUPPORTS_TOP_K:-false}"

echo "[1/3] Checking FRP model health: ${HEALTH_URL}"
curl -fsS "${HEALTH_URL}" >/dev/null

echo "[2/3] Checking model list: ${MODELS_URL}"
curl -fsS "${MODELS_URL}" >/dev/null

echo "[3/3] Starting CoALA agent with COALA_LOCAL_API_BASE=${COALA_LOCAL_API_BASE}"
cd "${ROOT_DIR}"
exec python main.py
