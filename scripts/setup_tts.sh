#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MLX_AUDIO_REV="${MLX_AUDIO_REV:-ee0c65d12d0be748aed5fb8e1587dc7cc8f9e644}"
CUSTOM_MODEL="${TTS_MODEL:-mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit}"
CLONE_MODEL="${TTS_CLONE_MODEL:-mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16}"
WITH_CLONE_MODEL="${WITH_CLONE_MODEL:-0}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "[ERROR] MLX-Audio setup requires Apple Silicon macOS."
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "[ERROR] 未找到 uv 或 Homebrew。"
    exit 2
  fi
  brew install uv
fi

uv python install 3.11
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  uv venv --python 3.11 .venv
fi
PY="$ROOT/.venv/bin/python"

# Pin to a reviewed upstream commit so course production is reproducible.
uv pip install --python "$PY" \
  "git+https://github.com/Blaizzy/mlx-audio.git@${MLX_AUDIO_REV}"
uv pip install --python "$PY" -e .

echo "[tts] caching default CustomVoice model: $CUSTOM_MODEL"
"$PY" - "$CUSTOM_MODEL" "$CLONE_MODEL" "$WITH_CLONE_MODEL" <<'PY'
from huggingface_hub import snapshot_download
import sys

custom_model, clone_model, with_clone = sys.argv[1:]
snapshot_download(custom_model)
if with_clone == "1":
    print(f"[tts] caching clone model: {clone_model}")
    snapshot_download(clone_model)
PY

echo
echo "TTS 安装完成。"
echo "默认中文音色：Dylan"
echo "如需预缓存声音克隆模型：WITH_CLONE_MODEL=1 bash scripts/setup_tts.sh"
echo "课程流水线：bash scripts/run_course.sh examples/course.example.json"
