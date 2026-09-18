#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

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

if [[ "${SAAS_DISTRIBUTED_RENDER_ENABLED:-false}" != "true" ]]; then
  echo "Set SAAS_DISTRIBUTED_RENDER_ENABLED=true for both the SaaS API and center before starting distributed rendering." >&2
  exit 2
fi

DB_NAME="${SAAS_DB_NAME:-digital_human}"
DB_USER="${SAAS_DB_USER:-digital_human}"
DB_PASSWORD="${SAAS_DB_PASSWORD:-local-dev-only-password}"
DB_PORT="${SAAS_POSTGRES_HOST_PORT:-5432}"
REDIS_PORT="${SAAS_REDIS_HOST_PORT:-6379}"
export DATABASE_URL="${SAAS_HOST_DATABASE_URL:-postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${DB_PORT}/${DB_NAME}}"
export REDIS_URL="${SAAS_HOST_REDIS_URL:-redis://127.0.0.1:${REDIS_PORT}/0}"
export WORKER_BACKEND=redis
export STORAGE_BACKEND=local
export STORAGE_LOCAL_ROOT="${SAAS_HOST_STORAGE_ROOT:-$ROOT/workspace/saas-assets}"

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

if ! "$PYTHON_BIN" -c "import sqlalchemy, psycopg" >/dev/null 2>&1; then
  echo "Center executor dependencies are missing." >&2
  echo "Install with: uv pip install --python \"$PYTHON_BIN\" -e '.[saas]'" >&2
  exit 2
fi

echo "Distributed Render Center"
echo "  Database  : configured"
echo "  Storage   : ${STORAGE_BACKEND:-local}"
echo "  Contract  : ${SAAS_RENDER_CONTRACT_VERSION:-v1}"
echo "  Lease     : ${SAAS_DISTRIBUTED_LEASE_SECONDS:-120}s"
echo "  Max tries : ${SAAS_DISTRIBUTED_MAX_ATTEMPTS:-3}"
echo

exec "$PYTHON_BIN" -m app.saas.distributed_center
