#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${AUDIO8_RUNTIME_DIR:-$ROOT/vendor/Audio8_TTS/onnx_runtime_0_1b_int8}"
if [[ ! -f "$RUNTIME/.service.pid" ]]; then
  echo "Audio8 service is not running."
  exit 0
fi
PID="$(cat "$RUNTIME/.service.pid")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done
fi
rm -f "$RUNTIME/.service.pid"
echo "Audio8 service stopped."
