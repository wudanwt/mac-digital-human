#!/usr/bin/env bash
set -euo pipefail

# MuseTalk 1.5 CUDA bootstrap for Linux NVIDIA cloud workers.
# Default runtime is an isolated Python 3.10 venv so cloud-vendor Conda
# mirrors/configuration cannot break installation.
# Official MuseTalk recommendation: Python 3.10 + PyTorch 2.0.1 CUDA 11.8.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CUDA_VENDOR_DIR="${CUDA_VENDOR_DIR:-$ROOT/vendor/MuseTalk-CUDA}"
MUSETALK_REPO="${MUSETALK_REPO:-https://github.com/TMElyralab/MuseTalk.git}"
MUSETALK_CUDA_REV="${MUSETALK_CUDA_REV:-0a89dec45a0192b824e3cf4daf96c239440c5ed8}"
MUSETALK_VENV="${MUSETALK_CUDA_VENV:-$ROOT/.venv-musetalk-cuda}"
PYTHON310="${MUSETALK_PYTHON310:-}"

say() { printf '\n==> %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

command -v nvidia-smi >/dev/null || fail "nvidia-smi not found. Please start an NVIDIA GPU instance/image first."
command -v git >/dev/null || fail "git not found."

if [ -z "$PYTHON310" ]; then
  if command -v python3.10 >/dev/null 2>&1; then
    PYTHON310="$(command -v python3.10)"
  else
    if ! command -v uv >/dev/null 2>&1; then
      say "Installing uv bootstrap tool"
      BOOTSTRAP_PYTHON=""
      if command -v python >/dev/null 2>&1; then
        BOOTSTRAP_PYTHON="$(command -v python)"
      elif command -v python3 >/dev/null 2>&1; then
        BOOTSTRAP_PYTHON="$(command -v python3)"
      else
        fail "No bootstrap Python found to install uv"
      fi
      "$BOOTSTRAP_PYTHON" -m pip install --upgrade uv
    fi
    say "Installing managed Python 3.10"
    uv python install 3.10
    PYTHON310="$(uv python find 3.10)"
  fi
fi

"$PYTHON310" -c 'import sys; assert sys.version_info[:2] == (3,10), sys.version' || fail "MUSETALK_PYTHON310 must point to Python 3.10"

say "GPU"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

if ! command -v ffmpeg >/dev/null; then
  say "Installing ffmpeg"
  if command -v apt-get >/dev/null; then
    apt-get update -y
    apt-get install -y ffmpeg
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

if [ ! -x "$MUSETALK_VENV/bin/python" ]; then
  say "Creating isolated Python 3.10 venv: $MUSETALK_VENV"
  "$PYTHON310" -m venv "$MUSETALK_VENV"
fi

run() { "$MUSETALK_VENV/bin/python" -m "$@"; }

say "Installing PyTorch CUDA 11.8 build"
run pip install --upgrade pip setuptools wheel
run pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118

say "Installing MuseTalk requirements"
run pip install -r "$CUDA_VENDOR_DIR/requirements.txt"

say "Installing OpenMMLab dependencies"
run pip install --no-cache-dir -U openmim
PATH="$MUSETALK_VENV/bin:$PATH" mim install "mmcv==2.0.1"
PATH="$MUSETALK_VENV/bin:$PATH" mim install "mmdet==3.1.0"
# chumpy's legacy build imports pip from its build environment. Build it in
# the prepared venv first so mmpose does not trigger pip build isolation.
run pip install --no-build-isolation "chumpy==0.70"
PATH="$MUSETALK_VENV/bin:$PATH" mim install "mmpose==1.1.0"

say "Downloading MuseTalk weights"
(
  cd "$CUDA_VENDOR_DIR"
  mkdir -p models/musetalkV15 models/sd-vae models/whisper models/dwpose models/syncnet models/face-parse-bisent
  # The upstream downloader upgrades huggingface_hub beyond the version
  # required by MuseTalk's transformers pin and uses deprecated CLI flags.
  run pip install "huggingface_hub==0.30.2"
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download TMElyralab/MuseTalk \
    --local-dir models --include "musetalkV15/musetalk.json" "musetalkV15/unet.pth"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download stabilityai/sd-vae-ft-mse \
    --local-dir models/sd-vae --include "config.json" "diffusion_pytorch_model.bin"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download openai/whisper-tiny \
    --local-dir models/whisper --include "config.json" "pytorch_model.bin" "preprocessor_config.json"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download yzd-v/DWPose \
    --local-dir models/dwpose --include "dw-ll_ucoco_384.pth"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download ByteDance/LatentSync \
    --local-dir models/syncnet --include "latentsync_syncnet.pt"
  PATH="$MUSETALK_VENV/bin:$PATH" huggingface-cli download ManyOtherFunctions/face-parse-bisent \
    --local-dir models/face-parse-bisent --include "79999_iter.pth" "resnet18-5c106cde.pth"
)

say "Verifying CUDA from PyTorch"
"$MUSETALK_VENV/bin/python" - <<'PY'
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

MuseTalk repo   : $CUDA_VENDOR_DIR
MuseTalk Python : $MUSETALK_VENV/bin/python

Add this to .env.cuda-worker:
MUSETALK_CUDA_PYTHON=$MUSETALK_VENV/bin/python

Next:
  MUSETALK_CUDA_PYTHON=$MUSETALK_VENV/bin/python bash scripts/cloud/check_musetalk_cuda.sh

For an official smoke test:
  cd "$CUDA_VENDOR_DIR"
  PATH="$MUSETALK_VENV/bin:\$PATH" bash inference.sh v1.5 normal
EOF
