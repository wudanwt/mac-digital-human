# Mac MLX · MuseTalk SaaS 验收

本模式让 SaaS 控制面运行在 Docker 中，而真实数字人生成 Worker 直接运行在 Apple Silicon Mac 宿主机。

## 架构

```text
Browser
  |
Docker API :8918
  |-- PostgreSQL 127.0.0.1:5432
  |-- Redis      127.0.0.1:6379
  `-- ./workspace/saas-assets  <--- shared ---> Mac Host MLX Worker

Redis engine queues
  |-- avatar:render:mock      -> Docker Mock Worker
  `-- avatar:render:musetalk  -> Mac MuseTalk MLX Worker
```

Mock 与 MuseTalk 已按引擎隔离，不会互相抢任务。

## 1. 更新配置

第一次使用新配置时，建议把 `.env.saas.example` 中新增的本机桥接变量同步到 `.env.saas`：

```text
SAAS_DB_NAME=digital_human
SAAS_DB_USER=digital_human
SAAS_DB_PASSWORD=local-dev-only-password
SAAS_POSTGRES_HOST_PORT=5432
SAAS_REDIS_HOST_PORT=6379
SAAS_SHARED_WORKSPACE_DIR=./workspace
SAAS_SHARED_OUTPUTS_DIR=./outputs
```

## 2. 启动 SaaS 控制面

真实 MLX 验收时可以不启动 Mock Worker：

```bash
docker compose --env-file .env.saas -f docker-compose.saas.yml up -d --build
```

如果也希望同时保留 Mock 验收：

```bash
docker compose --env-file .env.saas -f docker-compose.saas.yml --profile mock-worker up -d --build
```

两种 Worker 可以同时在线，因为任务队列已隔离。

## 3. 启动 Mac MLX Worker

在仓库根目录执行：

```bash
bash scripts/saas/start_mlx_worker_mac.sh
```

脚本会自动覆盖容器内连接地址，使用：

- PostgreSQL `127.0.0.1:${SAAS_POSTGRES_HOST_PORT:-5432}`
- Redis `127.0.0.1:${SAAS_REDIS_HOST_PORT:-6379}`
- 本地对象存储 `./workspace/saas-assets`
- `WORKER_BACKEND=redis`
- `SAAS_RENDERER=mlx-local`
- MuseTalk 队列 `avatar:render:musetalk`

启动前会运行 `python -m app.saas.mlx_preflight`，检查：

- Apple Silicon / arm64
- FFmpeg
- PostgreSQL
- Redis
- 共享素材目录
- MuseTalk MLX 模型与依赖文件
- CosyVoice 2 模型

全部通过后才进入 Worker 循环。

## 4. 界面验证

打开：

```text
http://127.0.0.1:8918
```

课程工作室第 4 步“生成引擎”会读取 `/api/saas/workers/status` 心跳：

- `Mac MLX · MuseTalk` 显示 `Worker 在线` 时才可选择。
- Worker 退出后心跳约 20 秒自动过期，界面会显示 `Worker 未启动`。
- Mock Worker 状态同理。

## 5. 真实生成链路

```text
PPT/PDF
 -> 页面解析与渲染
 -> 逐页讲稿
 -> CosyVoice 2 克隆语音
 -> MuseTalk 1.5 MLX 数字人口型
 -> PPT / 数字人 / 背景排版
 -> 字幕
 -> FFmpeg 合成
 -> MP4
 -> SaaS Output Asset
 -> 在线预览 / 下载
```

## 6. 常见问题

### 5432 或 6379 已被占用

在 `.env.saas` 修改：

```text
SAAS_POSTGRES_HOST_PORT=15432
SAAS_REDIS_HOST_PORT=16379
```

Mac Worker 启动脚本会自动读取对应端口。

### 预检提示 MuseTalk 不完整

执行原本项目的 MuseTalk MLX 安装/模型准备流程，并确认 `MuseTalkMLXEngine.readiness()` 中所有检查为 true。

### 预检提示 CosyVoice 不完整

确认 `digital-human-tts/models/CosyVoice2-0.5B/flow.pt` 存在，并使用包含 CosyVoice 依赖的 Python 环境运行 Worker。

### SaaS 上传了素材但 Worker 看不到

确认 Docker Compose 使用的是本分支的新 bind mount，而不是旧的 named volume：

```text
./workspace:/app/workspace
```

然后重新 `docker compose up -d --build`。
