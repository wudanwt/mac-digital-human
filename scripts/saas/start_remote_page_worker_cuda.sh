#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${CUDA_WORKER_ENV_FILE:-$ROOT/.env.cuda-worker}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing CUDA Worker env: $ENV_FILE" >&2
  echo "Copy .env.cuda-worker.example to .env.cuda-worker and configure it first." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${REMOTE_WORKER_API_BASE:?REMOTE_WORKER_API_BASE is required}"
: "${REMOTE_WORKER_TOKEN:?REMOTE_WORKER_TOKEN is required on Linux CUDA workers}"

export REMOTE_WORKER_RENDER_BACKEND=cuda
export REMOTE_WORKER_MODEL_VERSION="${REMOTE_WORKER_MODEL_VERSION:-musetalk-cuda}"
export SAAS_TTS_PREFETCH=0
export VIDEO_ENCODER_BACKEND="${VIDEO_ENCODER_BACKEND:-auto}"
export MUSETALK_CUDA_VIDEO_ENCODER="${MUSETALK_CUDA_VIDEO_ENCODER:-$VIDEO_ENCODER_BACKEND}"
export MUSETALK_CUDA_STREAMING="${MUSETALK_CUDA_STREAMING:-1}"
export MUSETALK_CUDA_RESIDENT="${MUSETALK_CUDA_RESIDENT:-1}"
export MUSETALK_CUDA_RESIDENT_FALLBACK="${MUSETALK_CUDA_RESIDENT_FALLBACK:-1}"
export MUSETALK_CUDA_MASTER_CACHE_ITEMS="${MUSETALK_CUDA_MASTER_CACHE_ITEMS:-2}"

bash "$ROOT/scripts/cloud/check_musetalk_cuda.sh"

PYTHON="${CUDA_WORKER_PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "Worker Python not found: $PYTHON" >&2
  echo "Create .venv and install the project with .[saas,matting,cosyvoice]." >&2
  exit 2
fi

"$PYTHON" - <<'PY'
import platform
import onnxruntime as ort
import torch

from app.video_encoding import video_encoder_info

if platform.system() != "Linux":
    raise SystemExit("CUDA remote Worker requires Linux")
if not torch.cuda.is_available():
    raise SystemExit(
        "Main Worker Python cannot see CUDA. Install a CUDA-enabled PyTorch build "
        "so CosyVoice TTS also runs on NVIDIA GPU."
    )
providers = ort.get_available_providers()
if "CUDAExecutionProvider" not in providers:
    raise SystemExit(
        "ONNX Runtime CUDAExecutionProvider is unavailable. "
        f"Available providers: {providers}. Re-run scripts/cloud/setup_cuda_worker_runtime.sh."
    )
print("Worker torch:", torch.__version__)
print("Worker CUDA :", torch.version.cuda)
print("Worker GPU  :", torch.cuda.get_device_name(0))
encoder = video_encoder_info()
print("Worker ORT  :", ort.__version__)
print("ORT EPs     :", ", ".join(providers))
print("Video encoder requested:", encoder["requested"])
print("Video encoder selected :", encoder["selected"])
print("FFmpeg NVENC available :", encoder["ffmpeg_h264_nvenc"])
print("FFmpeg NVENC usable    :", encoder["ffmpeg_h264_nvenc_usable"])
PY

exec "$PYTHON" -m app.saas.remote_page_worker
