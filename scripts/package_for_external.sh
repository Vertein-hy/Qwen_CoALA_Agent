#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
OUT_DIR="${1:-$HOME/dockerdata/transfer}"
STAMP="$(date +%Y%m%d_%H%M%S)"
PKG="Qwen_CoALA_Agent_external_${STAMP}.tar.gz"

mkdir -p "$OUT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cp -a "$ROOT_DIR" "$TMP_DIR/Qwen_CoALA_Agent"
rm -rf \
  "$TMP_DIR/Qwen_CoALA_Agent/.git" \
  "$TMP_DIR/Qwen_CoALA_Agent/.pytest_cache" \
  "$TMP_DIR/Qwen_CoALA_Agent/__pycache__" \
  "$TMP_DIR/Qwen_CoALA_Agent/data/chroma_db" \
  "$TMP_DIR/Qwen_CoALA_Agent/data/logs"

tar -C "$TMP_DIR" -czf "$OUT_DIR/$PKG" Qwen_CoALA_Agent

echo "Bundle created: $OUT_DIR/$PKG"
echo "Transfer it to external machine and unpack:"
echo "  tar -xzf $PKG"
echo "  cd Qwen_CoALA_Agent"
echo "  cp deploy/ipc_external/coala.env.example deploy/ipc_external/coala.env"
echo "  bash deploy/ipc_external/devctl.sh up"
