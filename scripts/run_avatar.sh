#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "请先运行: bash scripts/setup.sh"
  exit 2
fi
cd "$ROOT"
exec "$PY" -m app.cli "$@"
