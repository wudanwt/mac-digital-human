#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORKER_ENV="${CUDA_WORKER_CONDA_ENV:-digital-human-worker}"
PYTORCH_INDEX="${CUDA_WORKER_TORCH_INDEX:-https://download.pytorch.org/whl/cu118}"

fail() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*"; }

command -v conda >/dev/null 2>&1 || fail "conda not found"
command -v git >/dev/null 2>&1 || fail "git not found"

if ! conda env list | awk '{print $1}' | grep -qx "$WORKER_ENV"; then
  say "Creating Python 3.11 worker environment: $WORKER_ENV"
  conda create -y -n "$WORKER_ENV" python=3.11
fi

run() { conda run --no-capture-output -n "$WORKER_ENV" "$@"; }

say "Installing CUDA-enabled PyTorch for CosyVoice / matting"
run python -m pip install --upgrade pip setuptools wheel
run python -m pip install   torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1   --index-url "$PYTORCH_INDEX"

say "Installing SaaS Worker dependencies"
run python -m pip install -e '.[saas,matting,cosyvoice]'

say "Preparing portrait matting model"
run python scripts/setup_matting.py

say "Preparing CosyVoice 2 model"
run python scripts/setup_tts_models.py

say "Verifying main Worker CUDA runtime"
run python - <<'PY'
import sys
import torch

print("python:", sys.version.split()[0])
print("python_executable:", sys.executable)
print("torch:", torch.__version__)
print("cuda_runtime:", torch.version.cuda)
print("cuda_available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("Worker PyTorch cannot see CUDA")
print("gpu:", torch.cuda.get_device_name(0))
print("vram_gb:", round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2))
PY

WORKER_PYTHON="$(conda run -n "$WORKER_ENV" python -c 'import sys; print(sys.executable)' | tail -n 1)"

cat <<EOF

CUDA Worker application runtime is ready.

MuseTalk runtime : ${MUSETALK_CONDA_ENV:-musetalk-cuda} (Python 3.10 / official MuseTalk)
Worker runtime   : $WORKER_ENV (Python 3.11 / CosyVoice + SaaS)
Worker Python    : $WORKER_PYTHON

Add this to .env.cuda-worker:
CUDA_WORKER_PYTHON=$WORKER_PYTHON
EOF
