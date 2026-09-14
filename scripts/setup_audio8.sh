#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

AUDIO8_REV="${AUDIO8_REV:-07e40f5d0b03fc473635ef378654bfb581027ac3}"
AUDIO8_MODEL="${AUDIO8_MODEL:-Audio8/audio8-TTS-0.1B-ONNX-INT8}"
VENDOR="$ROOT/vendor/Audio8_TTS"
RUNTIME="$VENDOR/onnx_runtime_0_1b_int8"
MODEL_DIR="$RUNTIME/model"

if ! command -v git >/dev/null 2>&1; then
  echo "[ERROR] git is required"
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python 3.10+ is required"
  exit 2
fi

mkdir -p "$ROOT/vendor"
if [[ ! -d "$VENDOR/.git" ]]; then
  echo "[audio8] cloning Edge0-AI/Audio8_TTS"
  git clone https://github.com/Edge0-AI/Audio8_TTS.git "$VENDOR"
fi

git -C "$VENDOR" fetch --all --tags
git -C "$VENDOR" checkout "$AUDIO8_REV"

# Use the project's Python as the seed interpreter when available, but let the
# official runtime create and own its isolated .venv.
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Audio8 requires Python 3.10+")
PY

if [[ ! -d "$MODEL_DIR" || ! -f "$MODEL_DIR/runtime_manifest.json" ]]; then
  echo "[audio8] downloading $AUDIO8_MODEL"
  "$PYTHON_BIN" -m pip install -U huggingface_hub >/dev/null
  "$PYTHON_BIN" - "$AUDIO8_MODEL" "$MODEL_DIR" <<'PY'
from huggingface_hub import snapshot_download
import sys
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])
PY
else
  echo "[audio8] model already present: $MODEL_DIR"
fi

if [[ ! -f "$MODEL_DIR/runtime_manifest.json" ]]; then
  echo "[ERROR] Audio8 model download incomplete: runtime_manifest.json missing" >&2
  exit 2
fi

if [[ ! -x "$RUNTIME/.venv/bin/python" ]]; then
  echo "[audio8] creating isolated ONNX runtime environment"
  PYTHON_BIN="$PYTHON_BIN" bash "$RUNTIME/setup.sh"
else
  echo "[audio8] isolated runtime already exists"
fi

if [[ ! -d "$RUNTIME/voices/default" ]]; then
  echo "[audio8] registering bundled default voice"
  "$RUNTIME/.venv/bin/python" "$RUNTIME/scripts/register_default_voice.py"
fi

echo
echo "Audio8 0.1B INT8 ONNX 安装完成。"
echo "runtime: $RUNTIME"
echo "model:   $MODEL_DIR"
echo "启动服务: bash scripts/start_audio8.sh"
echo "停止服务: bash scripts/stop_audio8.sh"
echo "课程默认 provider: audio8"
