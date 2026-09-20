#!/usr/bin/env bash
set -euo pipefail

# 1. 切换到项目根目录
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="/opt/homebrew/bin:$PATH"

echo "========================================================"
echo " 🚀 启动本机 M5 Pro Remote Worker (macbook-m5pro-wudan)"
echo "========================================================"

# 2. 检查并加载本机专用环境变量
if [[ -f .env.remote-worker ]]; then
  echo "📄 加载配置文件: .env.remote-worker"
  set -a
  # shellcheck disable=SC1091
  source .env.remote-worker
  set +a
else
  echo "⚠️ 未找到 .env.remote-worker，将使用默认配置运行"
fi

# 确保辅助任务优先调度（试听/抠像优先由本机响应）
export REMOTE_WORKER_AUXILIARY_MODE="${REMOTE_WORKER_AUXILIARY_MODE:-preferred}"
export REMOTE_WORKER_NAME="${REMOTE_WORKER_NAME:-macbook-m5pro-wudan}"
export REMOTE_WORKER_RENDER_BACKEND="${REMOTE_WORKER_RENDER_BACKEND:-mlx}"

# 3. 检查 Python 虚拟环境
PYTHON_BIN="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "❌ 未检测到可用的 Python 环境，请检查 .venv" >&2
    exit 1
  fi
fi

# 4. 清理可能因异常退出残留的实例锁文件
LOCK_DIR="$ROOT/workspace/.remote-worker-locks"
if [[ -d "$LOCK_DIR" ]]; then
  rm -f "$LOCK_DIR"/*.lock 2>/dev/null || true
fi

mkdir -p "$ROOT/workspace" "$ROOT/outputs"

echo "📍 节点名称: $REMOTE_WORKER_NAME"
echo "🌐 中心地址: ${REMOTE_WORKER_API_BASE:-http://192.168.1.127:8918/api/saas/internal/render}"
echo "⚡ 调度模式: $REMOTE_WORKER_AUXILIARY_MODE (试听/抠像优先)"
echo "--------------------------------------------------------"
echo "提示: 按 Ctrl + C 即可停止 Worker"
echo "--------------------------------------------------------"

# 5. 执行 Worker 主入口（前台运行，实时输出日志）
exec "$PYTHON_BIN" -m app.saas.remote_page_worker
