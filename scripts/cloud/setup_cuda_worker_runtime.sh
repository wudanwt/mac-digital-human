#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORKER_VENV="${CUDA_WORKER_VENV:-$ROOT/.venv-cuda-worker}"
PYTORCH_INDEX="${CUDA_WORKER_TORCH_INDEX:-https://download.pytorch.org/whl/cu118}"

fail() { echo "ERROR: $*" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*"; }

command -v git >/dev/null 2>&1 || fail "git not found"

if command -v apt-get >/dev/null 2>&1; then
  say "Ensuring system packages and CJK fonts are installed"
  apt-get update -qq && apt-get install -y -qq fonts-noto-cjk ffmpeg
fi

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
"$PY" -m pip install \
  torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 \
  --index-url "$PYTORCH_INDEX"

say "Installing SaaS Worker dependencies"
"$PY" -m pip install -e '.[saas,matting,cosyvoice]'

say "Pinning CUDA Worker compatibility stack"
"$PY" -m pip install \
  "numpy==1.26.4" \
  "diffusers==0.29.0" \
  "transformers==4.51.3" \
  "modelscope==1.20.0" \
  "wetext==0.0.4" \
  "rembg==2.0.67"

# CPU and GPU ONNX Runtime distributions expose the same Python module and
# must not coexist. Remove whatever rembg/cosyvoice extras pulled in first.
"$PY" -m pip uninstall -y onnxruntime onnxruntime-gpu >/dev/null 2>&1 || true

# PyTorch 2.3.1 in this Worker uses CUDA 11.8/cuDNN 8. Use the matching
# official ONNX Runtime CUDA-11 feed instead of the default CUDA-12 wheel.
"$PY" -m pip install "onnxruntime-gpu==1.20.1" \
  --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/

say "Verifying ONNX Runtime CUDA provider"
"$PY" - <<'PY'
import onnxruntime as ort
providers = ort.get_available_providers()
print("onnxruntime:", ort.__version__)
print("providers:", providers)
if "CUDAExecutionProvider" not in providers:
    raise SystemExit(
        "CUDAExecutionProvider is unavailable. The Worker would fall back to CPU "
        "for CosyVoice speech-token extraction, so installation is stopped."
    )
PY

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
