#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

echo "=== 正在准备 CosyVoice 2.0 高保真语音克隆模型权重 ==="
"$PY" scripts/setup_tts_models.py

echo
echo "=== 正在检查 CosyVoice 2.0 语音运行时 ==="
"$PY" scripts/check_tts.py --provider cosyvoice2

echo
echo "TTS 准备就绪。生产环境使用 CosyVoice 2.0。"

