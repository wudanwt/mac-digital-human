#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CUDA_VENDOR_DIR="${CUDA_VENDOR_DIR:-$ROOT/vendor/MuseTalk-CUDA}"
MUSETALK_VENV="${MUSETALK_CUDA_VENV:-$ROOT/.venv-musetalk-cuda}"
PYTHON="${MUSETALK_CUDA_PYTHON:-$MUSETALK_VENV/bin/python}"

# Use the same FFmpeg selection logic as the production CUDA Worker.
# shellcheck disable=SC1091
source "$ROOT/scripts/cloud/select_cuda_ffmpeg.sh"

printf '=== NVIDIA GPU ===\n'
nvidia-smi --query-gpu=name,memory.total,utilization.gpu,driver_version --format=csv,noheader

printf '\n=== FFmpeg ===\n'
echo "path=$(command -v ffmpeg)"
ffmpeg -version | head -n 1
echo "configuration=$(ffmpeg -hide_banner -version 2>/dev/null | sed -n '3p')"

if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'h264_nvenc'; then
  echo 'h264_nvenc=available'
  _nvenc_error="$(mktemp)"
  if ffmpeg -hide_banner -loglevel error -f lavfi -i 'color=c=black:s=64x64:r=25:d=0.04' \
      -frames:v 1 -c:v h264_nvenc -f null - >/dev/null 2>"$_nvenc_error"; then
    echo 'h264_nvenc_usable=true'
  else
    echo 'h264_nvenc_usable=false'
    echo '--- NVENC smoke-test error ---'
    cat "$_nvenc_error"
    echo '--- NVIDIA encode libraries ---'
    ldconfig -p 2>/dev/null | grep -E 'libnvidia-encode|libcuda' || true
    if [ "${CUDA_REQUIRE_NVENC:-0}" = "1" ]; then
      rm -f "$_nvenc_error"
      echo 'CUDA_REQUIRE_NVENC=1; refusing to continue with libx264.' >&2
      exit 1
    fi
    echo 'WARNING: CUDA Worker will fall back to libx264.'
  fi
  rm -f "$_nvenc_error"
else
  echo 'h264_nvenc=missing'
  if [ "${CUDA_REQUIRE_NVENC:-0}" = "1" ]; then
    echo 'CUDA_REQUIRE_NVENC=1; refusing to continue without h264_nvenc.' >&2
    exit 1
  fi
  echo 'WARNING: CUDA Worker will fall back to libx264.'
fi

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

printf '\n=== CUDA Performance V2 runner ===\n'
for runner in \
  "$ROOT/scripts/cloud/musetalk_cuda_stream.py" \
  "$ROOT/scripts/cloud/musetalk_cuda_resident.py"; do
  if [ -f "$runner" ]; then
    "$PYTHON" -m py_compile "$runner"
    echo "OK   $runner"
  else
    echo "MISS $runner" >&2
    exit 1
  fi
done

printf '\n=== MuseTalk files ===\n'
TORCH_HUB_DIR="$("$PYTHON" -c 'import torch; print(torch.hub.get_dir())')"
required=(
  "$CUDA_VENDOR_DIR/inference.sh"
  "$CUDA_VENDOR_DIR/models/musetalkV15/unet.pth"
  "$CUDA_VENDOR_DIR/models/musetalkV15/musetalk.json"
  "$CUDA_VENDOR_DIR/models/whisper/pytorch_model.bin"
  "$CUDA_VENDOR_DIR/models/sd-vae/diffusion_pytorch_model.bin"
  "$CUDA_VENDOR_DIR/models/dwpose/dw-ll_ucoco_384.pth"
  "$CUDA_VENDOR_DIR/models/face-parse-bisent/79999_iter.pth"
  "$CUDA_VENDOR_DIR/models/face-parse-bisent/resnet18-5c106cde.pth"
  "$CUDA_VENDOR_DIR/models/syncnet/latentsync_syncnet.pt"
  "$CUDA_VENDOR_DIR/musetalk/utils/face_detection/detection/sfd/sfd.pth"
  "$TORCH_HUB_DIR/checkpoints/s3fd-619a316812.pth"
)
failed=0
for path in "${required[@]}"; do
  if [ -s "$path" ]; then
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
