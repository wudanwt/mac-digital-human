#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BRANCH="${CUDA_WORKER_BRANCH:-feat/cuda-resident-v3}"
ENV_FILE="${CUDA_WORKER_ENV_FILE:-$ROOT/.env.cuda-worker}"
CHECK_ONLY=0
SKIP_GIT=0

usage() {
  cat <<'EOF'
Usage: bash scripts/cloud/resume_cuda_worker.sh [--check-only] [--skip-git]

Resume an already-provisioned CUDA Worker after a cloud snapshot/restart.

This script intentionally NEVER runs pip, conda, apt, setup_musetalk_cuda.sh,
or setup_cuda_worker_runtime.sh. Missing dependencies cause a clear failure
instead of modifying the saved environment.

Options:
  --check-only  Pull/check the environment but do not start the Worker.
  --skip-git    Do not fetch/checkout/pull the configured branch.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    --skip-git) SKIP_GIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

echo "=== CUDA Worker resume ==="
echo "Repository : $ROOT"
echo "Branch     : $BRANCH"
echo "Env file   : $ENV_FILE"
echo

[ -d "$ROOT/.git" ] || { echo "ERROR: not a Git repository: $ROOT" >&2; exit 2; }
[ -f "$ENV_FILE" ] || {
  echo "ERROR: missing $ENV_FILE" >&2
  echo "Restore the saved .env.cuda-worker; do not recreate the Worker token unnecessarily." >&2
  exit 2
}

if [ "$SKIP_GIT" != "1" ]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: tracked files have local changes; refusing to overwrite them." >&2
    git status --short >&2
    echo "Commit/stash/review the changes first, then rerun resume_cuda_worker.sh." >&2
    exit 2
  fi

  echo "==> Syncing application code only (no package installation)"
  git fetch origin "$BRANCH"

  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
  else
    git checkout -b "$BRANCH" --track "origin/$BRANCH"
  fi

  git pull --ff-only origin "$BRANCH"
fi

echo
echo "==> Current revision"
git status -sb
git log -1 --oneline

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

CUDA_WORKER_PYTHON="${CUDA_WORKER_PYTHON:-$ROOT/.venv-cuda-worker/bin/python}"
MUSETALK_CUDA_PYTHON="${MUSETALK_CUDA_PYTHON:-$ROOT/.venv-musetalk-cuda/bin/python}"
export CUDA_WORKER_PYTHON MUSETALK_CUDA_PYTHON

for runtime in "$CUDA_WORKER_PYTHON" "$MUSETALK_CUDA_PYTHON"; do
  if [ ! -x "$runtime" ]; then
    echo "ERROR: saved CUDA runtime is missing: $runtime" >&2
    echo "The resume script will not reinstall it automatically." >&2
    exit 2
  fi
done

echo
echo "==> Selecting an existing FFmpeg/NVENC runtime"
# shellcheck disable=SC1091
source "$ROOT/scripts/cloud/select_cuda_ffmpeg.sh"

echo
echo "==> Main Worker CUDA / ONNX verification"
"$CUDA_WORKER_PYTHON" - <<'PY'
import onnxruntime as ort
import torch

providers = ort.get_available_providers()
print("python runtime :", __import__("sys").executable)
print("torch          :", torch.__version__)
print("torch cuda     :", torch.version.cuda)
print("cuda available :", torch.cuda.is_available())
print("gpu            :", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE")
print("onnxruntime    :", ort.__version__)
print("ORT providers  :", providers)

if not torch.cuda.is_available():
    raise SystemExit("ERROR: CUDA is unavailable in the main Worker runtime")
if "CUDAExecutionProvider" not in providers:
    raise SystemExit("ERROR: CUDAExecutionProvider is unavailable in ONNX Runtime")
PY

echo
echo "==> MuseTalk / NVENC readiness"
bash "$ROOT/scripts/cloud/check_musetalk_cuda.sh"

if [ "$CHECK_ONLY" = "1" ]; then
  echo
  echo "CUDA Worker snapshot environment is ready. Worker was not started (--check-only)."
  exit 0
fi

echo
echo "==> Starting CUDA Remote Worker"
exec bash "$ROOT/scripts/saas/start_remote_page_worker_cuda.sh"
