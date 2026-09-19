#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PATH="/opt/homebrew/bin:$PATH"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This launcher requires an Apple Silicon Mac (Darwin arm64)." >&2
  exit 2
fi

if [[ -f .env.remote-worker ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.remote-worker
  set +a
fi

export SAAS_TTS_PREFETCH=0
export REMOTE_WORKER_NAME="${REMOTE_WORKER_NAME:-$(scutil --get ComputerName 2>/dev/null || hostname)}"
export REMOTE_WORKER_RENDER_CONTRACT_VERSION="${REMOTE_WORKER_RENDER_CONTRACT_VERSION:-v1}"
export REMOTE_WORKER_CODE_VERSION="${REMOTE_WORKER_CODE_VERSION:-0.5.0}"
export REMOTE_WORKER_MODEL_VERSION="${REMOTE_WORKER_MODEL_VERSION:-musetalk-mlx}"
export REMOTE_WORKER_CACHE_GB="${REMOTE_WORKER_CACHE_GB:-20}"
export REMOTE_WORKER_MIN_DISK_FREE_GB="${REMOTE_WORKER_MIN_DISK_FREE_GB:-10}"
export REMOTE_WORKER_TRANSFER_SLOTS="${REMOTE_WORKER_TRANSFER_SLOTS:-2}"
export REMOTE_WORKER_UPLOAD_CHUNK_MB="${REMOTE_WORKER_UPLOAD_CHUNK_MB:-8}"
export REMOTE_WORKER_CACHE_DIR="${REMOTE_WORKER_CACHE_DIR:-$ROOT/workspace/remote-worker-cache}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  :
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Python was not found. Create .venv or set PYTHON_BIN." >&2
  exit 2
fi

mkdir -p "$REMOTE_WORKER_CACHE_DIR" "$ROOT/workspace" "$ROOT/outputs"

if ! "$PYTHON_BIN" -c "import httpx, psutil, sqlalchemy" >/dev/null 2>&1; then
  echo "Remote worker dependencies are missing." >&2
  echo "Install with: uv pip install --python \"$PYTHON_BIN\" -e '.[saas,matting,cosyvoice]'" >&2
  exit 2
fi

if [[ -z "${REMOTE_WORKER_API_BASE:-}" ]]; then
  REMOTE_WORKER_API_BASE="$("$PYTHON_BIN" -m app.saas.remote_worker_agent config --field api_base)"
  export REMOTE_WORKER_API_BASE
fi

if [[ -z "${REMOTE_WORKER_TOKEN:-}" ]]; then
  CREDENTIAL_SOURCE="macOS Keychain"
else
  CREDENTIAL_SOURCE="environment"
fi

echo "Remote Page Worker"
echo "  Center API : $REMOTE_WORKER_API_BASE"
echo "  Node       : $REMOTE_WORKER_NAME"
echo "  Contract   : $REMOTE_WORKER_RENDER_CONTRACT_VERSION"
echo "  Cache      : $REMOTE_WORKER_CACHE_DIR (${REMOTE_WORKER_CACHE_GB}GB)"
echo "  Disk guard : ${REMOTE_WORKER_MIN_DISK_FREE_GB}GB"
echo "  Credential : $CREDENTIAL_SOURCE"
echo "  TTS prefetch: disabled"
echo

echo "Running Apple-Silicon model preflight..."
"$PYTHON_BIN" -m app.saas.mlx_preflight --remote-api "$REMOTE_WORKER_API_BASE"

echo
echo "Preflight passed. Starting API-only page worker..."
exec "$PYTHON_BIN" -m app.saas.remote_page_worker
