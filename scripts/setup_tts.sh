#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROVIDER="${TTS_PROVIDER:-audio8}"

case "$PROVIDER" in
  audio8)
    bash scripts/setup_audio8.sh
    ;;
  qwen3)
    bash scripts/setup_qwen3_tts.sh
    ;;
  both)
    bash scripts/setup_audio8.sh
    bash scripts/setup_qwen3_tts.sh
    ;;
  *)
    echo "[ERROR] TTS_PROVIDER must be audio8, qwen3, or both" >&2
    exit 2
    ;;
esac

echo
echo "TTS 安装完成。默认课程 provider: audio8"
echo "只装 Qwen3: TTS_PROVIDER=qwen3 bash scripts/setup_tts.sh"
echo "两套都装: TTS_PROVIDER=both bash scripts/setup_tts.sh"
echo "课程流水线: bash scripts/run_course.sh examples/course.example.json"
