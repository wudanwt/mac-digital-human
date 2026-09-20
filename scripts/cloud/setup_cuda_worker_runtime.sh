#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORKER_VENV="${CUDA_WORKER_VENV:-$ROOT/.venv-cuda-worker}"
PYTORCH_INDEX="${CUDA_WORKER_TORCH_INDEX:-https://download.pytorch.org/whl/cu118}"

fail() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*"; }

command -v git >/dev/null 2>&1 || fail "git not found"

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

say "Preparing Python 3.11"
uv python install 3.11

if [ ! -x "$WORKER_VENV/bin/python" ]; then
  say "Creating Python 3.11 worker venv: $WORKER_VENV"
  uv venv --python 3.11 --seed "$WORKER_VENV"
fi

PY="$WORKER_VENV/bin/python"

say "Installing CUDA-enabled PyTorch for CosyVoice / matting"
"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install   torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1   --index-url "$PYTORCH_INDEX"

say "Installing SaaS Worker dependencies"
"$PY" -m pip install -e '.[saas,matting,cosyvoice]'

say "Preparing portrait matting model"
"$PY" scripts/setup_matting.py

say "Preparing CosyVoice 2 model"
"$PY" scripts/setup_tts_models.py

say "Verifying main Worker CUDA runtime"
"$PY" - <<'PY'
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

cat <<EOF

CUDA Worker application runtime is ready.

Worker Python : $PY

Add this to .env.cuda-worker:
CUDA_WORKER_PYTHON=$PY
EOF
