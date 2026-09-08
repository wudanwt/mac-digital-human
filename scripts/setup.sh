#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MLX_REV="${MLX_REV:-c6eb30ebd1ed4d043983209813370153de9346bf}"
MUSETALK_REV="${MUSETALK_REV:-8ca7d1884cf5c1c766dcd0365b069c96d75707cf}"
VARIANT="${VARIANT:-q8}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "[WARN] 本安装器针对 Apple Silicon macOS 设计。"
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "[ERROR] 未找到 Homebrew。请先安装 Homebrew: https://brew.sh"
  exit 2
fi

for pkg in ffmpeg uv git; do
  if ! command -v "$pkg" >/dev/null 2>&1; then
    echo "[brew] installing $pkg"
    brew install "$pkg"
  fi
done

echo "[python] preparing Python 3.11"
uv python install 3.11
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  uv venv --python 3.11 .venv
fi
PY="$ROOT/.venv/bin/python"

uv pip install --python "$PY" -e .

mkdir -p vendor models workspace outputs samples

clone_pinned() {
  local url="$1"
  local dir="$2"
  local rev="$3"
  if [[ ! -d "$dir/.git" ]]; then
    git clone "$url" "$dir"
  fi
  git -C "$dir" fetch --all --tags
  git -C "$dir" checkout "$rev"
}

echo "[vendor] MuseTalk-MLX"
clone_pinned "https://github.com/xocialize/musetalk-mlx.git" "$ROOT/vendor/musetalk-mlx" "$MLX_REV"

echo "[vendor] MuseTalk upstream"
clone_pinned "https://github.com/jjt997/musetalk.git" "$ROOT/vendor/MuseTalk" "$MUSETALK_REV"

uv pip install --python "$PY" -e "$ROOT/vendor/musetalk-mlx"

# Minimal Mac preprocessing stack. Do not install the original CUDA/MMCV/MMPose stack.
uv pip install --python "$PY" \
  torch torchvision \
  rtmlib onnxruntime \
  gdown pillow scipy requests

"$PY" scripts/setup_models.py --variant "$VARIANT"

echo
"$PY" scripts/check_runtime.py --variant "$VARIANT" || true

echo
echo "安装完成。"
echo "CLI: bash scripts/run_avatar.sh --video samples/master.mp4 --audio samples/voice.wav"
echo "Web: bash scripts/run_web.sh"
