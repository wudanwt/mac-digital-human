#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CUDA_VENDOR_DIR="${CUDA_VENDOR_DIR:-$ROOT/vendor/MuseTalk-CUDA}"
MUSETALK_VENV="${MUSETALK_CUDA_VENV:-$ROOT/.venv-musetalk-cuda}"
PYTHON="${MUSETALK_CUDA_PYTHON:-$MUSETALK_VENV/bin/python}"

printf '=== NVIDIA GPU ===\n'
nvidia-smi --query-gpu=name,memory.total,utilization.gpu,driver_version --format=csv,noheader

printf '\n=== FFmpeg ===\n'
ffmpeg -version | head -n 1

if [ ! -x "$PYTHON" ]; then
  echo "MuseTalk CUDA Python not found: $PYTHON" >&2
  exit 1
fi

printf '\n=== MuseTalk Python ===\n'
"$PYTHON" - <<'PY'
import sys
import torch
print('python=', sys.version.split()[0])
print('torch=', torch.__version__)
print('cuda_available=', torch.cuda.is_available())
print('cuda_runtime=', torch.version.cuda)
if torch.cuda.is_available():
    print('gpu=', torch.cuda.get_device_name(0))
    print('vram_gb=', round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2))
PY

printf '\n=== MuseTalk files ===\n'
required=(
  "$CUDA_VENDOR_DIR/inference.sh"
  "$CUDA_VENDOR_DIR/models/musetalkV15/unet.pth"
  "$CUDA_VENDOR_DIR/models/musetalkV15/musetalk.json"
  "$CUDA_VENDOR_DIR/models/whisper/pytorch_model.bin"
  "$CUDA_VENDOR_DIR/models/sd-vae/diffusion_pytorch_model.bin"
)
failed=0
for path in "${required[@]}"; do
  if [ -e "$path" ]; then
    echo "OK   $path"
  else
    echo "MISS $path"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  echo '\nMuseTalk CUDA environment is incomplete.' >&2
  exit 1
fi

echo '\nMuseTalk CUDA environment looks ready.'
