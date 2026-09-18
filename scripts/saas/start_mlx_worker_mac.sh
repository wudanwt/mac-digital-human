#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This launcher requires an Apple Silicon Mac (Darwin arm64)." >&2
  exit 2
fi

load_dotenv() {
  local file="$1" line key value first last
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#export }"
    [[ "$line" == *"="* ]] || continue

    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue

    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ ( "$first" == '"' && "$last" == '"' ) || ( "$first" == "'" && "$last" == "'" ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi

    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$file"
}

if [[ -f .env.saas ]]; then
  load_dotenv .env.saas
fi

DB_NAME="${SAAS_DB_NAME:-digital_human}"
DB_USER="${SAAS_DB_USER:-digital_human}"
DB_PASSWORD="${SAAS_DB_PASSWORD:-local-dev-only-password}"
DB_PORT="${SAAS_POSTGRES_HOST_PORT:-5432}"
REDIS_PORT="${SAAS_REDIS_HOST_PORT:-6379}"

export DATABASE_URL="${SAAS_HOST_DATABASE_URL:-postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}}"
export REDIS_URL="${SAAS_HOST_REDIS_URL:-redis://127.0.0.1:${REDIS_PORT}/0}"
export WORKER_BACKEND=redis
export SAAS_RENDERER=mlx-local
export STORAGE_BACKEND=local
export STORAGE_LOCAL_ROOT="${SAAS_HOST_STORAGE_ROOT:-$ROOT/workspace/saas-assets}"
export U2NET_HOME="${U2NET_HOME:-$ROOT/workspace/saas-matting-models}"
export AVATAR_MATTING_BACKEND="${AVATAR_MATTING_BACKEND:-auto}"
export AVATAR_MATTING_TORCH_MODEL_DIR="${AVATAR_MATTING_TORCH_MODEL_DIR:-$ROOT/workspace/saas-matting-models/pytorch/BiRefNet-portrait}"

mkdir -p "$STORAGE_LOCAL_ROOT" "$U2NET_HOME" "$ROOT/workspace" "$ROOT/outputs"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  if [[ "$PYTHON_BIN" == */* ]]; then
    if [[ ! -x "$PYTHON_BIN" ]]; then
      echo "PYTHON_BIN is not executable: $PYTHON_BIN" >&2
      exit 2
    fi
  elif ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "PYTHON_BIN was not found on PATH: $PYTHON_BIN" >&2
    exit 2
  fi
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Python was not found. Create .venv or set PYTHON_BIN to a Python 3 executable." >&2
  exit 2
fi

echo "Mac MLX SaaS Worker"
echo "  Database : configured"
echo "  Redis    : configured"
echo "  Storage  : $STORAGE_LOCAL_ROOT"
echo "  Queue    : ${SAAS_QUEUE_NAME:-avatar:render}:musetalk"
echo "  Matting  : ${AVATAR_MATTING_MODEL:-birefnet-portrait}"
echo "  Backend  : $AVATAR_MATTING_BACKEND"
echo "  Python   : $PYTHON_BIN"
echo

if ! "$PYTHON_BIN" -c "import psycopg, redis, sqlalchemy, cv2, rembg, torch, torchvision, transformers" >/dev/null 2>&1; then
  echo "The selected Python environment is missing SaaS or portrait-matting dependencies." >&2
  echo "Install them with:" >&2
  echo "  uv pip install --python \"$PYTHON_BIN\" -e '.[saas,matting]'" >&2
  exit 2
fi

echo "Running preflight..."
"$PYTHON_BIN" -m app.saas.mlx_preflight

echo
echo "Preflight passed. Starting MuseTalk MLX + transparent-avatar worker..."
exec "$PYTHON_BIN" -m app.saas.worker_entry
