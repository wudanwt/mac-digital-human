# 微课数字人项目生产集群部署交接文档 (Cluster Deployment Handoff)

> **版本**：v1.0
> **更新时间**：2026-09-19
> **状态**：API、调度中心及两台远程 Worker 已启动；账号和平台默认素材已迁移，真实人物抠像任务已通过 MPS 验收。

## 2026-09-19 账号与默认素材迁移实况

- 群晖代码已更新至本机 `codex/remote-aux-workers` 工作树快照，数据库迁移至 `0012_auxiliary_task_leases`。该工作树包含尚未提交的生产配置修复，不能仅凭 GitHub 分支重建出完全相同的镜像。
- 仅迁入 2 个账号、2 个工作区及成员关系、2 条当前订阅；未迁移付款订单、订阅历史、课程、租户私有素材或历史成片。密码哈希与本机一致。生产配置的 `SAAS_ADMIN_EMAILS` 已设为 `ops-admin@example.com`，该账号保有超级管理员权限。
- 平台默认素材目录为 7 个数字人（宁雅、小白、明明、朵朵、老白、若琳、阿曼达）与 6 张背景，不含丹哥。相关媒体已导入 MinIO，27 个模板引用文件逐一通过 SHA-256 与大小校验；两个迁入账号访问目录 API 均得到 13 项。
- 为避免“目录已迁移但数字人页为空”，13 项默认素材已经实际导入两个现有工作区。`ops-admin@example.com` 与 `wudanwt@163.com` 的前端业务接口均返回 7 个数字人和 6 张背景；后续新增租户仍按需从平台默认素材目录导入。
- API 健康接口返回 HTTP 200，容器 `healthy`、重启 0 次；调度中心进程运行、重启 0 次。调度中心没有 HTTP 监听，生产 Compose 已禁用从 API 镜像继承的 HTTP 健康检查。
- 群晖迁移前数据库与代码备份、迁移包位于 `/volume3/docker/mac-digital-human-backups/account-assets-migration-20260919/`；生产 `.env.production` 的修改前副本也在其中。备份包含敏感配置及密码哈希，须限制访问。
- 两台 M4 Worker 已同步当前 Worker 代码并接入群晖：`m4-mini-ergou` 与 `m4-mini-adab` 均报告 `online`、空闲槽位 `0/1`、代码版本 `0.5.0`、模型版本 `musetalk-mlx`、协议 `v1`，能力包含页面渲染、语音试听、人物抠像及透明数字人合成。两端预检均通过 Apple Silicon、FFmpeg、MuseTalk MLX、CosyVoice、人物抠像与 Center API 检查，人物抠像后端均为 `pytorch-mps-fp16`。
- SSH 会话无法写入 macOS 登录钥匙串，因此本次使用每节点独立、可吊销的 `wrk_...` 凭据，保存在各节点权限 `0600` 的 `.env.remote-worker` 中；生成和传输用的明文临时文件已删除。两端原配置与代码备份分别保存在各自的 `~/worker-backups/20260919-before-nas-enrollment/`，目录权限为 `0700`。
- Worker 已通过注册、心跳、页面任务轮询与辅助任务轮询验收。2026-09-19 导入数字人“朵朵”后的首条抠像任务因两端虚拟环境缺少 `rembg` 失败；现已在两端安装完整 `matting` 依赖，并修改远程预检使其强制验证抠像依赖，避免缺依赖的节点继续上线接单。
- “朵朵”已使用 `m4-mini-ergou` 的 `pytorch-mps-fp16` 后端重新处理成功：251 帧、耗时 349.81 秒，透明视频、抠图海报和白底预览三项资产均已写入对象存储并登记入库。两台 Worker 的 MPS 与 ONNX 备用模型文件均完成 SHA-256 一致性校验。真实语音试听与完整课程成片仍需另行验收。

以下第 4 节与后续步骤保留了迁移前的故障记录与操作背景；其中“API 不健康”的描述不是当前状态。

---

## 1. 生产集群架构与角色矩阵

```mermaid
graph TD
    Client[客户端/外部访问] -->|8918 API / 9005 MinIO| Syno[群晖 NAS 主中心<br>192.168.1.234]

    subgraph Synology_NAS [群晖 NAS (192.168.1.234 / volume3)]
        API[API 服务<br>Port: 8918]
        Center[分布式调度中心<br>distributed_center]
        PG[(PostgreSQL 17<br>Port: 5432)]
        RD[(Redis 缓存/队列<br>Port: 6379)]
        MinIO[(MinIO 对象存储<br>API: 9005 / Console: 9006)]

        API --> PG
        API --> RD
        API --> MinIO
        Center --> PG
        Center --> RD
    end

    subgraph M4_Worker_1 [Mac mini M4 节点 1]
        Worker1[Remote Page Worker V3]
        Jump[SSH 中继入口<br>nas.5dpc.top:8022 / 192.168.1.64]
    end

    subgraph M4_Worker_2 [Mac mini M4 节点 2]
        Worker2[Remote Page Worker V3<br>192.168.1.89]
    end

    Worker1 -->|HTTP 心跳与任务轮询| API
    Worker2 -->|HTTP 心跳与任务轮询| API
```

### 节点资产清单

| 角色 | 局域网 IP | 外网/映射端口 | 登录账号 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| **群晖 NAS (主中心)** | `192.168.1.234` | DSM 5001 / API 8918 / MinIO 9005, 9006 | `admin` | 部署 Docker Compose 集群，所有持久化数据挂载至 `/volume3` |
| **Mac mini M4 (节点 1)** | `192.168.1.64` | `nas.5dpc.top:8022` | `ergou` | 跳板中继机 + 本地渲染 Worker 1（LaunchAgent 托管） |
| **Mac mini M4 (节点 2)** | `192.168.1.89` | 局域网内通 | `adab` | 本地渲染 Worker 2（LaunchAgent 托管） |

---

## 2. 已完成的核心操作与基础设施变更

### 2.1 互联互通与免密配置
* **Mac 1 → 群晖 NAS**：已通过 `ssh-copy-id` 写入公钥，Mac 1 上执行 `ssh admin@192.168.1.234` 已完全免密。
* **Mac 1 → Mac 2**：已打通 SSH 免密通道，Mac 1 上执行 `ssh adab@192.168.1.89` 已免密。
* **群晖 NAS 权限升级**：
  * 在 `/etc/sudoers.d/admin-nopasswd` 注入了 `admin ALL=(ALL) NOPASSWD: ALL`，普通命令无需交互输入 sudo 密码。
  * 将 `/usr/local/bin/docker` 与 `/usr/local/bin/docker-compose` 软链接至 `/usr/bin/`，彻底解决非交互 SSH 的 `PATH` 找不到命令问题。

### 2.2 群晖存储空间与生产环境定义
* **避开满盘存储卷**：群晖 `/volume1` 已经 100% 满盘，所有生产集群持久化卷已统一建在 `/volume3/docker/mac-digital-human/`：
  * `postgres_data/`、`redis_data/`、`minio_data/`、`workspace/`、`outputs/`
* **强随机生产环境变量**：已生成并在群晖放置 `.env.production`，包含独立的 `SAAS_DB_PASSWORD`、`STORAGE_ACCESS_KEY`、`STORAGE_SECRET_KEY`、`JWT_SECRET` 等。

### 2.3 Docker 构建性能与编排优化
* **MinIO 官方源修正**：Docker Hub 的 `minio/minio` 缺少新版本的 `latest` 标签，编排文件已切换为官方 Quay 镜像：
  * `quay.io/minio/minio:latest` 与 `quay.io/minio/mc:latest`。
* **规避端口冲突**：群晖 9000 端口已被既有的 `portainer` 占用，MinIO API 映射调整为 `9005:9000`，控制台映射为 `9006:9001`。
* **Dockerfile 极致优化**：
  * 移除导致报错中断的 `# syntax=docker/dockerfile:1.7` 声明；
  * Debian 基础源替换为阿里云镜像（秒级装完 `ffmpeg`、`libreoffice`、中文字体）；
  * pip 源替换为 `https://mirrors.aliyun.com/pypi/simple/`，避免了国外源网络抖动。
* **镜像编译完成**：生产镜像 `mac-digital-human-api:prod` 已 100% 成功导出并保存在群晖 Docker 镜像列表中。

---

## 3. 踩坑记录与排查要点 (Pitfalls)

1. **本地 SSH 连接 Mac 1 被拒绝 (`Too many authentication failures`)**：
   * 本地客户端若有多个 SSH key，SSH 默认会全部尝试导致被远程 `sshd` 直接踢掉。
   * **解决规则**：发起 SSH 时必须强制指定参数：`-o IdentitiesOnly=yes -o PubkeyAuthentication=no`。
2. **群晖 NAS `/volume1` 爆满**：
   * 严禁在 `/volume1` 进行任何文件写入或挂载，否则会导致容器写失败或群晖系统告警。
3. **macOS 命令行切换 `systemsetup -setremotelogin` 陷阱**：
   * 在 macOS 新系统（Sonoma/Sequoia）上，终端未获“完全磁盘访问权限 (Full Disk Access)”时，执行 `sudo systemsetup -setremotelogin on` 会静默失败或提示权限不足，导致远程登录被误关闭。
   * **替代方案**：使用 `sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist` 直接管理守护进程。

---

## 4. 当前运行状态诊断

> 2026-09-20 更新：下列服务已经恢复，早期的 API `unhealthy` 问题不再存在。

1. **镜像状态**：`mac-digital-human-api:prod` 已经构建并部署成功。
2. **容器状态**：`postgres`、`redis`、`minio`、`api` 均健康，`distributed-center` 正常运行。
3. **浏览器媒体访问**：生产环境使用私有 MinIO。`STORAGE_PUBLIC_BASE_URL=http://192.168.1.234:9005` 供 Worker 获取短时签名 URL；用户浏览器的头像、母版、声音、成片和透明资产预览统一走认证后的同源 `/api/saas/assets/{id}/content`。课程文稿确认页的 PPT 分页缩略图也由 `/api/saas/course-tools/ppt/{asset_id}/slides/{index}/thumbnail` 同源转发，不再 307 跳转到 MinIO。这样可避免 Docker 内部域名、跨域双重认证、HTTPS 混合内容、非标准端口拦截以及 `connect-src 'self'` CSP 拦截。
4. **数据验收**：账号工作区包含 1 门课程、7 个数字人和 31 个素材；课程 `course` 关联“若琳”且 3 页文稿完整；“朵朵”的透明资产已完成（251 帧），透明 PNG 与白底视频均可预览。
5. **局域网链路**：当前可直接访问 NAS `192.168.1.234` 和两台 Mac Worker；日常浏览及 Worker 通信不需要公网跳板。NAS SSH 若从当前开发机握手被群晖策略重置，可经 `192.168.1.64` 管理，但这不影响应用流量。
6. **画面排版背景**：内置背景、工作区已上传/已导入背景和画面排版中新上传的背景，都通过同源素材接口生成 Blob 预览；选中后会写入当前页的 `background_asset_id` / `custom_bg` 并立即保存。不要恢复为直接请求 MinIO 签名地址，否则会再次触发 CSP 或双重认证问题。

历史健康检查定义如下：
3. **健康检查定义**（`docker-compose.prod.yml`）：
   ```yaml
   command: ["sh", "-c", "alembic upgrade head && exec uvicorn app.saas_main:app --host 0.0.0.0 --port 8918 --proxy-headers --forwarded-allow-ips='*'"]
   healthcheck:
     test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8918/api/saas/health || exit 1"]
     interval: 15s
     timeout: 5s
     start_period: 30s
     retries: 3
   ```
   API 当前已通过该健康检查。

---

## 5. 后续接手与上线实操手册 (Runbook)

### 步骤 1：恢复 Mac 1 的 SSH 监听
在第一台 Mac mini（`192.168.1.64`）终端中执行：
```bash
sudo launchctl bootstrap system /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || sudo launchctl load -w /System/Library/LaunchDaemons/ssh.plist
```
*(或在系统设置 → 通用 → 共享中开启「远程登录」)*

### 步骤 2：在群晖查看 API 容器真实报错
在 Mac 1 上免密登录群晖执行：
```bash
ssh admin@192.168.1.234 "sudo docker logs --tail 100 mac-digital-human-prod-api"
```

### 步骤 3：修复并拉起容器集群
若发现是 Alembic 初始迁移未完成，可在群晖进入项目目录手动执行：
```bash
ssh admin@192.168.1.234
cd /volume3/docker/mac-digital-human

# 1. 重新启动服务
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d

# 2. 手动在容器中运行迁移与初始化
sudo docker exec mac-digital-human-prod-api alembic upgrade head
sudo docker exec mac-digital-human-prod-api python -m app.saas.bootstrap

# 3. 验证 API 健康检查
curl -fsS http://127.0.0.1:8918/api/saas/health
```

### 步骤 4：生成两台 Mac mini Worker 认证 Token
在群晖 API 容器内生成 Worker 节点接入凭据：
```bash
# 生成 Mac 1 凭据
sudo docker exec mac-digital-human-prod-api python -m app.saas.manage create-worker --name m4-mini-ergou --slots 1

# 生成 Mac 2 凭据
sudo docker exec mac-digital-human-prod-api python -m app.saas.manage create-worker --name m4-mini-adab --slots 1
```
记录返回的两个 `wrk_...` 令牌字符串。

### 步骤 5：配置两台 Mac mini 并重启 Worker

#### ① 配置 Mac 1 (ergou)
在 Mac 1 终端写入 `/Users/ergou/mac-digital-human/.env.remote-worker`：
```ini
REMOTE_WORKER_API_BASE=http://192.168.1.234:8918/api/saas/internal/render
REMOTE_WORKER_NAME=m4-mini-ergou
REMOTE_WORKER_TOKEN=<填入上面生成的m4-mini-ergou-TOKEN>
REMOTE_WORKER_CONCURRENCY=1
REMOTE_WORKER_OUTPUT_DIR=/Users/ergou/mac-digital-human/outputs
```
重启服务：
```bash
launchctl unload ~/Library/LaunchAgents/com.mac-digital-human.remote-page-worker.plist
launchctl load -w ~/Library/LaunchAgents/com.mac-digital-human.remote-page-worker.plist
```

#### ② 配置 Mac 2 (adab)
从 Mac 1 免密登录 Mac 2 配置：
```bash
ssh adab@192.168.1.89
cat << 'EOF' > /Users/adab/mac-digital-human/.env.remote-worker
REMOTE_WORKER_API_BASE=http://192.168.1.234:8918/api/saas/internal/render
REMOTE_WORKER_NAME=m4-mini-adab
REMOTE_WORKER_TOKEN=<填入上面生成的m4-mini-adab-TOKEN>
REMOTE_WORKER_CONCURRENCY=1
REMOTE_WORKER_OUTPUT_DIR=/Users/adab/mac-digital-human/outputs
EOF

launchctl unload ~/Library/LaunchAgents/com.mac-digital-human.remote-page-worker.plist
launchctl load -w ~/Library/LaunchAgents/com.mac-digital-human.remote-page-worker.plist
```

### 步骤 6：集群最终验收命令
在群晖上运行以下命令，验证两台 Worker 是否均处于就绪状态：
```bash
sudo docker exec mac-digital-human-prod-api python -c '
from app.saas.database import SessionLocal
from app.saas.distributed_render_models import WorkerNode
db = SessionLocal()
for node in db.query(WorkerNode).all():
    print(f"节点名: {node.name} | 状态: {node.status} | 最近心跳: {node.heartbeat_at}")
'
```
当两台节点状态均显示为 `online` 时，即代表生产分布式微课集群已全部就绪！
