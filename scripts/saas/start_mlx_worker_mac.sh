#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This launcher requires an Apple Silicon Mac (Darwin arm64)." >&2
  exit 2
fi

# Load .env.saas as dotenv data, not as shell source code.
# Docker-style .env files legitimately allow unquoted values containing spaces
# (for example: SAAS_APP_NAME=Digital Human SaaS Studio), which `source` cannot.
# Existing shell environment variables always win over values from the file.
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

    # Remove one matching pair of surrounding quotes without evaluating the value.
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

mkdir -p "$STORAGE_LOCAL_ROOT" "$ROOT/workspace" "$ROOT/outputs"

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "Mac MLX SaaS Worker"
echo "  Database : $DATABASE_URL"
echo "  Redis    : $REDIS_URL"
echo "  Storage  : $STORAGE_LOCAL_ROOT"
echo "  Queue    : ${SAAS_QUEUE_NAME:-avatar:render}:musetalk"
echo

echo "Running preflight..."
"$PYTHON_BIN" -m app.saas.mlx_preflight

echo
echo "Preflight passed. Starting MuseTalk MLX worker..."
exec "$PYTHON_BIN" -m app.saas.worker_entry
