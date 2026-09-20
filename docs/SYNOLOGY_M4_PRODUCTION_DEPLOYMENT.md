# 群晖 + 双 Mac mini M4 数字人 SaaS 生产部署方案

> 文档状态：部署架构资产 / 生产化实施基线  
> 适用仓库：`wudanwt/mac-digital-human-saas`  
> 基线分支：`feat/remote-worker-enrollment-v3`  
> 目标环境：自有公网 IP + 自有域名 + 群晖 NAS + 2 台 Mac mini M4（16GB / 256GB）

---

## 1. 目标

在尽量不增加云服务器和云 GPU 成本的前提下，利用现有家用基础设施部署可长期运行的数字人 SaaS。

核心原则：

1. 群晖承担 7×24 小时在线的控制面、数据库、缓存和对象存储。
2. 两台 Mac mini M4 只承担数字人计算任务，不承载数据库和主站。
3. 公网仅暴露 HTTPS 入口，不直接暴露 PostgreSQL、Redis、FastAPI、MinIO 管理端口。
4. Mac Worker 统一通过公网/内网均可使用的 HTTPS Center API 主动连接，不依赖 Redis、PostgreSQL 或 SMB/NFS 共享目录。
5. 大文件使用 MinIO Signed URL 直传/直下，避免 FastAPI 成为视频传输瓶颈。
6. 一套域名即可，无需购买第二个域名；通过主域名 + 子域名区分 SaaS 与对象存储。

---

## 2. 推荐总体架构

```text
                           Internet
                              │
                        自有域名 / 公网 IP
                              │
                        Router / Firewall
                         仅转发 TCP 443
                              │
                              ▼
┌────────────────────────────────────────────────────┐
│                    Synology NAS                    │
│                                                    │
│  Reverse Proxy / TLS                               │
│        │                                           │
│        ├── SaaS API / Web :8918                    │
│        ├── Distributed Center                      │
│        ├── PostgreSQL                              │
│        ├── Redis                                   │
│        └── MinIO Object Storage                    │
│                                                    │
│  角色：Control Plane + Data Plane + Storage        │
└──────────────────────┬─────────────────────────────┘
                       │ HTTPS
              ┌────────┴─────────┐
              │                  │
              ▼                  ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Mac mini M4 #1       │  │ Mac mini M4 #2       │
│ 16GB / 256GB         │  │ 16GB / 256GB         │
│ Remote Worker        │  │ Remote Worker        │
│                      │  │                      │
│ CosyVoice 2          │  │ CosyVoice 2          │
│ MuseTalk MLX         │  │ MuseTalk MLX         │
│ FFmpeg               │  │ FFmpeg               │
│ 1 Compute Slot       │  │ 1 Compute Slot       │
└──────────────────────┘  └──────────────────────┘
```

---

## 3. 设备职责

| 设备 | 角色 | 运行内容 |
|---|---|---|
| 群晖 NAS | Center / 生产服务器 | Web、FastAPI、Distributed Center、PostgreSQL、Redis、MinIO、反向代理、备份 |
| Mac mini M4 #1 | Render Worker | CosyVoice 2、MuseTalk MLX、FFmpeg、页面级渲染 |
| Mac mini M4 #2 | Render Worker | CosyVoice 2、MuseTalk MLX、FFmpeg、页面级渲染 |
| 路由器 | 网络边界 | 仅将 WAN TCP 443 转发到群晖 |
| 域名 | 公网访问入口 | SaaS 主站与对象存储子域名 |

不建议让 Mac mini 同时承担数据库、Redis 或主站 API。这样 Mac 重启、模型升级或 Worker 故障时，不会导致整个 SaaS 离线。

---

## 4. 域名规划

只需要现有的一个域名。

假设现有域名为：

```text
example.com
```

推荐规划：

```text
https://example.com
    → SaaS 主站 / API

https://storage.example.com
    → MinIO S3-compatible API
```

其中 `storage.example.com` 只是 `example.com` 的子域名，不需要购买第二个域名。

也可以使用：

```text
https://saas.example.com
https://storage.example.com
```

但如果主域名目前没有其他网站，优先直接使用：

```text
example.com
storage.example.com
```

### 为什么对象存储使用独立子域名

仓库当前支持 S3/MinIO 的：

- `signed_get_url()`
- `signed_put_url()`

Signed URL 对 Host、Path 和签名一致性敏感。独立对象存储子域名可以避免 `/storage/` 路径改写导致的签名问题，并使 Worker 能直接与 MinIO 传输大文件。

---

## 5. DNS 与内外网解析

公网 DNS：

```text
example.com          A  → 家中公网 IP
storage.example.com  A  → 家中公网 IP
```

如果公网 IP 会变化，应在路由器或群晖上配置 DDNS/API 自动更新 DNS。

### 推荐 Split DNS

家中局域网内：

```text
example.com          → 群晖 LAN IP
storage.example.com  → 群晖 LAN IP
```

公网：

```text
example.com          → 家中公网 IP
storage.example.com  → 家中公网 IP
```

这样两台 Mac mini 在家中仍然访问统一域名，不依赖固定的 `192.168.x.x` 地址。

如果路由器支持 NAT Loopback / Hairpin NAT，也可以直接依赖公网 DNS 回环访问。

---

## 6. 公网端口原则

公网原则上只开放：

```text
TCP 443
```

路由器：

```text
WAN :443
   ↓
Synology :443
```

以下端口禁止直接暴露公网：

```text
5432  PostgreSQL
6379  Redis
8918  FastAPI
9000  MinIO API 内部端口
9001  MinIO Console
DSM   管理端口
```

公网访问全部经过 HTTPS Reverse Proxy。

---

## 7. 群晖建议运行的服务

建议使用 Synology Container Manager / Docker Compose 运行：

```text
postgres
redis
api
distributed-center
minio
```

建议容器关系：

```text
Reverse Proxy
   │
   ├── example.com
   │      ↓
   │   api:8918
   │
   └── storage.example.com
          ↓
       minio:9000

api
 ├── PostgreSQL
 ├── Redis
 └── MinIO

distributed-center
 ├── PostgreSQL
 ├── Redis
 └── MinIO
```

PostgreSQL、Redis 和 MinIO Console 只在 Docker 私有网络或 NAS 本机可访问。

---

## 8. MinIO 作为生产对象存储

本项目当前已经支持：

```text
local
s3
minio
oss
cos
```

MinIO 走 S3-compatible 适配层。

推荐生产配置方向：

```env
STORAGE_BACKEND=minio
STORAGE_BUCKET=digital-human
STORAGE_ENDPOINT=https://storage.example.com
STORAGE_SIGNED_URL_SECONDS=3600

AWS_ACCESS_KEY_ID=<minio-access-key>
AWS_SECRET_ACCESS_KEY=<minio-secret-key>

SAAS_DISTRIBUTED_DIRECT_DOWNLOADS=true
SAAS_DISTRIBUTED_DIRECT_UPLOADS=true
```

> 不要把真实密钥提交到 Git 仓库。

### 数据流

大文件推荐链路：

```text
Mac Worker
   │
   ├── HTTPS → Center
   │      register / heartbeat / claim / lease / progress / commit
   │
   └── Signed URL → MinIO
          GET 任务输入
          PUT page_audio
          PUT page_video
```

这样母版视频、PPT 渲染资产、逐页音频和逐页视频不需要通过 FastAPI 中转。

---

## 9. SaaS Center 生产配置基线

示例：

```env
SAAS_ENV=production

SAAS_ALLOW_PUBLIC_REGISTRATION=false
SAAS_JWT_SECRET=<32+ chars random secret>

SAAS_TRUSTED_HOSTS=example.com
SAAS_CORS_ORIGINS=https://example.com

WORKER_BACKEND=redis
SAAS_DISTRIBUTED_RENDER_ENABLED=true

SAAS_RENDER_CONTRACT_VERSION=v1
SAAS_DISTRIBUTED_EXPECTED_CODE_VERSION=0.5.0
SAAS_DISTRIBUTED_EXPECTED_MODEL_VERSION=musetalk-mlx

STORAGE_BACKEND=minio
STORAGE_BUCKET=digital-human
STORAGE_ENDPOINT=https://storage.example.com
STORAGE_SIGNED_URL_SECONDS=3600

SAAS_DISTRIBUTED_DIRECT_DOWNLOADS=true
SAAS_DISTRIBUTED_DIRECT_UPLOADS=true

SAAS_REQUIRE_AI_LABEL=true
```

数据库与 Redis 使用容器内部地址，不使用公网 IP。

---

## 10. 两台 Mac mini M4 的部署方式

两台 Mac 均使用当前 Remote Worker V3 模式。

原则：

- Worker 主动访问 Center。
- Worker 不直接连接 PostgreSQL。
- Worker 不直接连接 Redis。
- Worker 不保存 MinIO 永久凭据。
- Worker 不依赖 NAS SMB/NFS 路径。
- Worker Token 存入 macOS Keychain。
- 使用 LaunchAgent 自动启动。

### 每台机器 1 个 Compute Slot

对于 M4 16GB：

```text
Mac mini #1 → 1 slot
Mac mini #2 → 1 slot
```

不要在 16GB 机器上强行运行两个并行 MuseTalk Compute Slot。

两台机器形成：

```text
Worker Pool
├── macmini-m4-01  1 slot
└── macmini-m4-02  1 slot

Total = 2 compute slots
```

---

## 11. Worker Enrollment

管理员在 Center 创建一次性注册码：

```bash
python -m app.saas.manage create-worker-enrollment \
  --name macmini-m4-01 \
  --slots 1
```

第二台：

```bash
python -m app.saas.manage create-worker-enrollment \
  --name macmini-m4-02 \
  --slots 1
```

目标 Mac：

```bash
python -m app.saas.remote_worker_agent enroll \
  --center https://example.com/api/saas/internal/render \
  --name macmini-m4-01 \
  --install
```

第二台同理。

Enrollment 成功后：

- 长期 Worker credential 写入 macOS Keychain。
- 本地配置文件不保存长期 Token。
- Enrollment Code 使用一次后失效。
- LaunchAgent 安装并启动 Worker。
- Center 可以 Drain / Resume / Revoke Worker。

---

## 12. Mac Worker 本地缓存建议

当前默认值为：

```env
REMOTE_WORKER_CACHE_GB=20
REMOTE_WORKER_MIN_DISK_FREE_GB=10
```

由于 M4 仅有 256GB SSD，建议生产初期使用：

```env
REMOTE_WORKER_CACHE_GB=12
REMOTE_WORKER_MIN_DISK_FREE_GB=25
```

原因：

- MuseTalk 模型
- CosyVoice 模型
- Python/uv 环境
- FFmpeg 临时文件
- 中间 WAV / MP4
- macOS 系统更新

都会消耗本地 SSD。

长期资产与最终成片应保存在 MinIO/NAS，而不是 Mac mini 本地磁盘。

---

## 13. HTTPS 与证书

群晖 Reverse Proxy 建议同时绑定：

```text
example.com
storage.example.com
```

并分别配置有效 TLS 证书。

Worker 公网模式必须使用 HTTPS。

不要在公网生产环境使用：

```env
REMOTE_WORKER_ALLOW_INSECURE_HTTP=1
```

---

## 14. 当前仓库与生产部署之间的差距

### 14.1 Remote Worker V3 当前状态

公网 Remote Worker V3 当前位于：

```text
feat/remote-worker-enrollment-v3
```

对应 Draft PR #10，尚未正式进入 `main`。

因此建议先在真实群晖 + 双 M4 环境进行验收，再决定合并。

### 14.2 当前 docker-compose.saas.yml 不是生产 Compose

当前文件明确定位为 Local / Acceptance Stack。

并且 API / Distributed Center 中仍存在：

```yaml
STORAGE_BACKEND: local
STORAGE_LOCAL_ROOT: /app/workspace/saas-assets
```

这会覆盖 `.env.saas` 中的生产对象存储配置。

因此不能直接将当前 `docker-compose.saas.yml` 当作群晖生产部署文件。

### 14.3 建议新增的生产资产

下一阶段应新增：

```text
docker-compose.prod.yml
.env.production.example
scripts/deploy/synology/
docs/SYNOLOGY_PRODUCTION_RUNBOOK.md
```

至少包含：

- PostgreSQL
- Redis
- API
- Distributed Center
- MinIO
- production environment validation
- healthcheck
- restart policy
- volume mapping
- backup scripts
- upgrade / rollback procedure

---

## 15. 备份策略

至少备份：

### PostgreSQL

每日：

```text
pg_dump
```

保留：

```text
7 日每日备份
4 周每周备份
3 月每月备份
```

### MinIO 数据

推荐：

- Synology Snapshot
- Hyper Backup
- 异地 NAS / 云存储二次备份

### 配置

备份但不要直接提交 Git：

- production env
- MinIO credentials
- TLS/Reverse Proxy 配置
- DNS/DDNS 配置

---

## 16. 高可用边界

当前方案定位为：

```text
低成本正式服务 / 小规模商业运行 / 内部生产
```

它不是传统双机房高可用架构。

主要单点：

- 家庭宽带
- 家庭供电
- 路由器
- 群晖 NAS
- 公网 IP 线路

建议逐步增加：

1. 群晖接 UPS。
2. 路由器接 UPS。
3. 群晖开启自动重启恢复。
4. Docker 服务设置 restart policy。
5. PostgreSQL 定时备份。
6. MinIO/NAS 做异地备份。
7. 后续业务量上升后再考虑云端 Center 迁移。

两台 Mac Worker 本身不存在单 Worker 单点；任一 Mac 下线时，另一个节点可以继续处理任务。

---

## 17. 推荐实施顺序

### Phase 1：代码生产化

- [ ] 新建 production Compose
- [ ] 移除生产环境中的 `STORAGE_BACKEND=local` 硬编码
- [ ] 增加 MinIO 服务定义
- [ ] 增加生产环境模板
- [ ] 增加 NAS 持久化卷
- [ ] 增加健康检查
- [ ] 增加数据库备份脚本

### Phase 2：群晖部署

- [ ] 安装 Container Manager
- [ ] 创建数据目录
- [ ] 部署 PostgreSQL
- [ ] 部署 Redis
- [ ] 部署 MinIO
- [ ] 部署 API
- [ ] 部署 Distributed Center

### Phase 3：域名与网络

- [ ] 主域名指向公网 IP
- [ ] 创建 `storage` 子域名
- [ ] 配置 DDNS（如需要）
- [ ] 配置群晖 Reverse Proxy
- [ ] 配置 HTTPS
- [ ] 路由器仅开放 TCP 443
- [ ] 验证外网访问

### Phase 4：Worker

- [ ] Mac #1 安装模型与运行环境
- [ ] Mac #2 安装模型与运行环境
- [ ] 创建 Enrollment Code
- [ ] 两台 Mac 完成 Enrollment
- [ ] 安装 LaunchAgent
- [ ] Center 显示双 Worker Online

### Phase 5：真实验收

- [ ] 上传 PPT/PDF
- [ ] 选择真实数字人
- [ ] 执行真实 CosyVoice TTS
- [ ] 执行真实 MuseTalk MLX
- [ ] 验证两台 Mac 都能 Claim Task
- [ ] 验证页面级任务分布
- [ ] 验证 MinIO direct GET
- [ ] 验证 MinIO direct PUT
- [ ] 验证 Signed URL 失败后 Center fallback
- [ ] 验证 Worker 重启恢复
- [ ] 验证单 Worker 下线后的任务恢复
- [ ] 验证最终 MP4 可预览和下载

---

## 18. 生产验收标准

上线前至少满足：

1. 公网扫描无法直接访问 PostgreSQL / Redis / 8918 / 9000 / 9001。
2. SaaS 仅通过 HTTPS 对外访问。
3. MinIO Bucket 为 Private。
4. Mac Worker 没有数据库、Redis、MinIO 永久凭据。
5. Worker credential 保存在 Keychain。
6. 两台 Worker 均能稳定心跳和 Claim。
7. 单台 Worker 退出后任务最终可恢复。
8. 页面输入下载后进行 size + SHA-256 校验。
9. 最终产物可从对象存储正确 materialize。
10. PostgreSQL 和 MinIO 均存在可验证恢复的备份。
11. 群晖重启后核心容器自动恢复。
12. Mac 登录/重启后 Worker 自动恢复，或明确记录无人值守限制。

---

## 19. 后续扩容方式

当前架构不需要因为增加算力而重构 Center。

后续可以继续增加：

```text
Mac mini M4 #3
Mac mini M4 #4
Mac Studio
异地 Apple Silicon Worker
```

统一通过：

```text
HTTPS Center API
+
Remote Worker Enrollment
+
Worker Pool
```

加入计算集群。

如果未来家庭网络成为瓶颈，可以只把 Center + PostgreSQL + Redis + 对象存储迁移到云端，两台或多台 Mac 仍继续作为 Remote Worker 使用。

---

## 20. 本方案最终推荐拓扑

```text
用户浏览器
    │
    ▼
https://example.com
    │
    ▼
Synology Reverse Proxy
    │
    ▼
SaaS API + Distributed Center
    │
    ├──────── PostgreSQL
    ├──────── Redis
    │
    └──────── MinIO
                 ▲
                 │ Signed GET / PUT
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
Mac mini M4 #1      Mac mini M4 #2
1 Compute Slot      1 Compute Slot
```

这是当前硬件条件下优先推荐的第一阶段生产架构。
