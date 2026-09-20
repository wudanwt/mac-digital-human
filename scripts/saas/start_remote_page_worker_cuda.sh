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

bash "$ROOT/scripts/cloud/check_musetalk_cuda.sh"

PYTHON="${CUDA_WORKER_PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "Worker Python not found: $PYTHON" >&2
  echo "Create .venv and install the project with .[saas,matting,cosyvoice]." >&2
  exit 2
fi

"$PYTHON" - <<'PY'
import platform
import torch

if platform.system() != "Linux":
    raise SystemExit("CUDA remote Worker requires Linux")
if not torch.cuda.is_available():
    raise SystemExit(
        "Main Worker Python cannot see CUDA. Install a CUDA-enabled PyTorch build "
        "so CosyVoice TTS also runs on NVIDIA GPU."
    )
print("Worker torch:", torch.__version__)
print("Worker CUDA :", torch.version.cuda)
print("Worker GPU  :", torch.cuda.get_device_name(0))
PY

exec "$PYTHON" -m app.saas.remote_page_worker
