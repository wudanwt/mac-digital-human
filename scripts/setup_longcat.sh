#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LONGCAT_REV="${LONGCAT_REV:-e2e1e8701424cef0e601281b62e228e5289ed032}"
VARIANT="${LONGCAT_VARIANT:-q4-merged}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "[ERROR] LongCat MLX setup requires Apple Silicon macOS."
  exit 2
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

uv python install 3.11
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  uv venv --python 3.11 .venv
fi
PY="$ROOT/.venv/bin/python"

mkdir -p vendor models/longcat workspace outputs

if [[ ! -d "$ROOT/vendor/longcat-avatar-mlx/.git" ]]; then
  echo "[vendor] cloning longcat-avatar-mlx"
  git clone https://github.com/xocialize/longcat-avatar-mlx.git "$ROOT/vendor/longcat-avatar-mlx"
fi

git -C "$ROOT/vendor/longcat-avatar-mlx" fetch --all --tags
git -C "$ROOT/vendor/longcat-avatar-mlx" checkout "$LONGCAT_REV"

# Install the orchestration app + LongCat runtime helpers, then the pinned MLX port.
# No CUDA / FlashAttention / Triton are installed on this path.
uv pip install --python "$PY" -e ".[longcat]"
uv pip install --python "$PY" -e "$ROOT/vendor/longcat-avatar-mlx"

"$PY" scripts/setup_longcat_models.py --variant "$VARIANT"

echo
"$PY" scripts/check_runtime.py --engine longcat --longcat-variant "$VARIANT" || true

echo
echo "LongCat Avatar 1.5 MLX 安装完成。"
echo "推荐：M5 Pro 48GB 使用 q4-merged。"
echo "Web: bash scripts/run_web.sh"
echo "CLI: bash scripts/run_avatar.sh --engine longcat --image samples/ref.png --audio samples/voice.wav --prompt 'A professional Chinese male instructor speaking naturally to camera'"
