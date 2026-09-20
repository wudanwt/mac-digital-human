#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

say() { printf '\n==> %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# 1. 检查虚拟环境
WORKER_VENV="${CUDA_WORKER_VENV:-$ROOT/.venv-cuda-worker}"
MUSE_VENV="${CUDA_MUSE_VENV:-$ROOT/.venv-musetalk-cuda}"

[ -x "$WORKER_VENV/bin/python" ] || fail "Worker Venv 不存在: $WORKER_VENV"
[ -x "$MUSE_VENV/bin/python" ] || fail "MuseTalk Venv 不存在: $MUSE_VENV"

say "检测 CUDA 运行环境与 GPU 状态"
"$WORKER_VENV/bin/python" - <<'PY'
import torch
import onnxruntime as ort

print("PyTorch CUDA available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("PyTorch 无法识别 CUDA 设备！")

providers = ort.get_available_providers()
print("ONNX Runtime providers:", providers)
if "CUDAExecutionProvider" not in providers:
    raise SystemExit("ONNX Runtime 缺失 CUDAExecutionProvider！")
PY

# 2. 检查环境变量配置
ENV_FILE="$ROOT/.env.cuda-worker"
if [ -f "$ENV_FILE" ]; then
    say "加载节点环境变量: $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# 3. 清理残留锁文件
rm -rf "$ROOT/workspace/.remote-worker-locks/"*

# 4. 检查并启动 MuseTalk Resident 守护进程
RESIDENT_LOG="$ROOT/workspace/musetalk-cuda-resident.log"
mkdir -p "$ROOT/workspace"

pkill -f 'musetalk_cuda_resident.py' || true
sleep 1

say "启动 MuseTalk 常驻推理守护进程 (Resident V3)..."
nohup "$MUSE_VENV/bin/python" "$ROOT/scripts/cloud/musetalk_cuda_resident.py" \
    --musetalk-dir "$ROOT/vendor/MuseTalk-CUDA" \
    --unet-model-path "$ROOT/vendor/MuseTalk-CUDA/models/musetalkV15/unet.pth" \
    --unet-config "$ROOT/vendor/MuseTalk-CUDA/models/musetalkV15/musetalk.json" \
    --whisper-dir "$ROOT/vendor/MuseTalk-CUDA/models/whisper" \
    --gpu-id 0 \
    --cache-items 2 \
    --cache-cpu-gb 6.0 \
    --cache-gpu-gb 4.0 \
    --use-float16 \
    >> "$RESIDENT_LOG" 2>&1 &

RESIDENT_PID=$!
echo "Resident PID: $RESIDENT_PID"

say "等待常驻守护进程就绪 (最多等待 30 秒)..."
READY=0
for i in $(seq 1 30); do
    if grep -q "ready" "$RESIDENT_LOG" 2>/dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -eq 1 ]; then
    say "MuseTalk 常驻进程就绪成功！"
else
    say "提示: 常驻进程在后台持续初始化中，查看: $RESIDENT_LOG"
fi

# 5. 启动远程 Page Worker 节点服务
say "启动 Remote Page Worker 节点服务并注册上线..."
exec "$WORKER_VENV/bin/python" -m app.saas.remote_page_worker
