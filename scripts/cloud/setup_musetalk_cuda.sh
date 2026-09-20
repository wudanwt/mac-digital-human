#!/usr/bin/env bash
set -euo pipefail

# MuseTalk 1.5 CUDA bootstrap for temporary domestic GPU instances
# Target: Ubuntu + NVIDIA driver + conda (common on MatPool/AutoDL images)
# Official MuseTalk recommendation: Python 3.10, CUDA 11.7/11.8-compatible PyTorch 2.0.1.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CUDA_VENDOR_DIR="${CUDA_VENDOR_DIR:-$ROOT/vendor/MuseTalk-CUDA}"
CONDA_ENV="${MUSETALK_CONDA_ENV:-musetalk-cuda}"
MUSETALK_REPO="${MUSETALK_REPO:-https://github.com/TMElyralab/MuseTalk.git}"
MUSETALK_CUDA_REV="${MUSETALK_CUDA_REV:-0a89dec45a0192b824e3cf4daf96c239440c5ed8}"
CONDA_CHANNEL="${CUDA_WORKER_CONDA_CHANNEL:-https://conda.anaconda.org/conda-forge}"

say() { printf '\n==> %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

command -v nvidia-smi >/dev/null || fail "nvidia-smi not found. Please start an NVIDIA GPU instance/image first."
command -v conda >/dev/null || fail "conda not found. Choose a GPU image with Miniconda/Anaconda preinstalled."
command -v git >/dev/null || fail "git not found."

say "GPU"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

if ! command -v ffmpeg >/dev/null; then
  say "Installing ffmpeg"
  if command -v apt-get >/dev/null; then
    sudo apt-get update -y || apt-get update -y
    sudo apt-get install -y ffmpeg || apt-get install -y ffmpeg
  else
    fail "ffmpeg missing and apt-get unavailable. Install ffmpeg manually."
  fi
fi

if [ ! -d "$CUDA_VENDOR_DIR/.git" ]; then
  say "Cloning official MuseTalk"
  mkdir -p "$(dirname "$CUDA_VENDOR_DIR")"
  git clone "$MUSETALK_REPO" "$CUDA_VENDOR_DIR"
else
  say "Refreshing official MuseTalk repository"
  git -C "$CUDA_VENDOR_DIR" fetch --all --tags
fi

say "Pinning official MuseTalk revision: $MUSETALK_CUDA_REV"
git -C "$CUDA_VENDOR_DIR" checkout "$MUSETALK_CUDA_REV"

if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
  say "Creating isolated Python 3.10 CUDA environment: $CONDA_ENV"
  conda create -y -n "$CONDA_ENV" --override-channels -c "$CONDA_CHANNEL" python=3.10 pip
fi

run() { conda run -n "$CONDA_ENV" "$@"; }

say "Installing PyTorch CUDA 11.8 build"
run python -m pip install --upgrade pip setuptools wheel
run python -m pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118

say "Installing MuseTalk requirements"
run python -m pip install -r "$CUDA_VENDOR_DIR/requirements.txt"

say "Installing OpenMMLab dependencies"
run python -m pip install --no-cache-dir -U openmim
run mim install mmengine
run mim install "mmcv==2.0.1"
run mim install "mmdet==3.1.0"
run mim install "mmpose==1.1.0"

say "Downloading MuseTalk weights"
(
  cd "$CUDA_VENDOR_DIR"
  # Official repository provides this script for Linux.
  conda run -n "$CONDA_ENV" bash ./download_weights.sh
)

say "Verifying CUDA from PyTorch"
run python - <<'PY'
import torch
print('torch:', torch.__version__)
print('cuda_available:', torch.cuda.is_available())
print('cuda_runtime:', torch.version.cuda)
if not torch.cuda.is_available():
    raise SystemExit('PyTorch cannot see CUDA GPU')
print('gpu:', torch.cuda.get_device_name(0))
print('vram_gb:', round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2))
PY

cat <<EOF

CUDA bootstrap completed.

MuseTalk repo : $CUDA_VENDOR_DIR
Conda env     : $CONDA_ENV

Next:
  bash scripts/cloud/check_musetalk_cuda.sh

For an official smoke test:
  cd "$CUDA_VENDOR_DIR"
  conda run -n "$CONDA_ENV" bash inference.sh v1.5 normal
EOF
