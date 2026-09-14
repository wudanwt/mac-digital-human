#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${AUDIO8_RUNTIME_DIR:-$ROOT/vendor/Audio8_TTS/onnx_runtime_0_1b_int8}"
if [[ ! -x "$RUNTIME/.venv/bin/python" ]]; then
  echo "Audio8 runtime 未安装。先运行: bash scripts/setup_audio8.sh" >&2
  exit 2
fi
PORT="${AUDIO8_PORT:-8024}" ARKTTS_THREADS="${AUDIO8_THREADS:-5}" bash "$RUNTIME/start_server.sh"
