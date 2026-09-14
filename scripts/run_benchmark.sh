#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "请先运行安装脚本。"
  exit 2
fi
cd "$ROOT"
exec "$PY" scripts/benchmark.py "$@"
