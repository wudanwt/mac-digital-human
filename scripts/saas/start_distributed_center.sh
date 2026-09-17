#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -f .env.saas ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.saas
  set +a
fi

export SAAS_DISTRIBUTED_RENDER_ENABLED="${SAAS_DISTRIBUTED_RENDER_ENABLED:-true}"

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
