# SaaS 云端版架构设计

> 分支：`feat/saas-cloud`
>
> 目标：在不破坏现有 Apple Silicon 本地版的前提下，把数字人微课生产链路拆成可多租户、可排队、可横向扩容、可接按量 GPU 的 SaaS 架构。

## 1. 现状与改造原则

当前本地版以 `FastAPI + 本机 JobManager + MuseTalk-MLX + CosyVoice + FFmpeg` 为核心，重任务在单机内串行执行。这个结构适合个人生产，但不适合多用户并发、跨机器调度和云端 GPU 弹性伸缩。

SaaS 改造遵循四个原则：

1. `main` 的本地工作流继续可用，不把云依赖强塞给桌面版。
2. 控制面与计算面分离：CPU API 常驻，GPU Worker 按需扩容。
3. 用户文件和生成结果进入对象存储，不依赖单机磁盘。
4. 所有生成任务都具备 tenant/user 边界，为后续套餐、额度、计费和企业空间做准备。

## 2. 目标架构

```text
Browser / App
     |
     v
SaaS API (FastAPI)
     |
     +---- PostgreSQL   用户 / 租户 / 套餐 / 任务历史 / 计费
     |
     +---- Redis        实时状态 / 任务队列 / 限流
     |
     +---- Object Store PPT / 母版 / 声音 / 中间件 / 成片
     |
     v
GPU Queue
     |
     +---- GPU Worker 1  MuseTalk CUDA
     +---- GPU Worker 2  MuseTalk CUDA
     +---- GPU Worker N  MuseTalk CUDA
     |
     v
FFmpeg / subtitles / composer
     |
     v
Object Store + CDN
```

精品模式后续单独增加 LongCat Worker，不与普通 MuseTalk 队列绑死。

## 3. 当前分支已经落地

### 3.1 独立 SaaS 入口

- `app/saas_main.py`
- 不直接改写现有 `app/main.py`
- 启动：`uvicorn app.saas_main:app --host 0.0.0.0 --port 8918`

### 3.2 多租户任务模型

- `app/saas/domain.py`
- 每个任务带 `tenant_id`、`user_id`
- 状态：`queued -> running -> succeeded / failed / canceled`
- API 查询会校验 tenant/user，避免跨租户读取任务

目前开发阶段用请求头模拟身份：

```text
X-Tenant-ID: demo-company
X-User-ID: dan
```

生产环境必须替换为 JWT / Session 鉴权后的可信 claims，不能相信客户端任意提交的租户头。

### 3.3 Redis 队列

- `app/saas/queue.py`
- 本地开发支持 `InMemoryJobQueue`
- 云端支持 `RedisJobQueue`
- API 与 GPU Worker 可以部署在不同机器

### 3.4 对象存储抽象

- `app/saas/storage.py`
- 本地开发：Local filesystem
- 云端：S3-compatible API
- 可对接 AWS S3、MinIO，以及提供 S3 兼容接口的 OSS/COS 网关方案

### 3.5 Worker 契约

- `app/saas/worker.py`
- Worker 从 Redis 取任务、更新状态、执行渲染、上传结果
- 已保留 `LocalMLXMuseTalkHandler`，方便 Mac 上联调整套 SaaS 控制面
- Linux GPU 生产 Worker 使用同一 `RenderHandler` 契约实现 `MuseTalk CUDA`

### 3.6 本地云化基础设施

- `Dockerfile.saas-api`
- `docker-compose.saas.yml`
- PostgreSQL 16
- Redis 7，开启 AOF
- CPU API 容器

复制环境变量模板：

```bash
cp .env.saas.example .env.saas
```

然后：

```bash
docker compose -f docker-compose.saas.yml up --build
```

## 4. API 第一版

健康检查：

```http
GET /api/saas/health
```

提交任务：

```http
POST /api/saas/jobs
X-Tenant-ID: demo-company
X-User-ID: dan
Content-Type: application/json

{
  "engine": "musetalk",
  "payload": {
    "video": "/path/to/master.mp4",
    "audio": "/path/to/voice.wav"
  }
}
```

查询任务：

```http
GET /api/saas/jobs/{job_id}
X-Tenant-ID: demo-company
X-User-ID: dan
```

当前 payload 仍允许本地路径，是为了先验证控制面与 Worker；云端正式版会改成对象存储 URI / asset_id，禁止客户端向 Worker 注入任意服务器路径。

## 5. 接下来必须完成的事项

### Phase A：SaaS 控制面

- PostgreSQL ORM 与 Alembic migration
- User / Tenant / Membership
- Asset / Avatar / VoiceProfile
- RenderJob 持久化
- JWT 登录与权限
- API rate limit
- 套餐、分钟额度、用量流水

### Phase B：Linux CUDA Worker

官方 MuseTalk 1.5 原生支持 Linux/CUDA，并提供 normal 与 realtime inference。生产 Worker 目标不是照搬 MLX，而是实现独立的 `MuseTalkCUDAHandler`：

```text
RenderHandler
  |- LocalMLXMuseTalkHandler      Mac 开发
  |- MuseTalkCUDAHandler          普通 SaaS
  `- LongCatCUDAHandler           精品生成（后续）
```

GPU Worker 镜像不安装 Web/UI，只包含：

- CUDA / PyTorch
- MuseTalk 1.5
- FFmpeg
- 下载/上传对象存储素材
- Redis queue client
- GPU benchmark / telemetry

### Phase C：素材云化

现有本地路径：

```text
profiles/assets/
workspace/
outputs/
```

替换为：

```text
asset://tenant/avatar/...
asset://tenant/voice/...
asset://tenant/course/...
asset://tenant/output/...
```

数据库只记录 asset metadata，文件本体放对象存储。

### Phase D：计费

不按“任务数”计费，建议按可理解的业务单位：

- 普通数字人生成分钟
- 精品数字人生成分钟
- 存储空间
- 企业讲师数量
- 并发优先级

底层同时记录 GPU seconds，方便计算毛利：

```text
job_gpu_seconds
job_video_seconds
queue_wait_seconds
render_factor = gpu_seconds / video_seconds
```

最终可以得到：

```text
每 1 分钟成片的 GPU 成本
每个套餐的真实毛利
何时从 Serverless GPU 切换为包月 GPU
```

## 6. 推荐的第一版生产部署

```text
1 x 2C4G/4C8G CPU API
1 x Managed PostgreSQL 或小规格 PostgreSQL
1 x Redis
1 x OSS/COS/S3 bucket
0..N x 按量 GPU Worker
CDN
```

GPU 空闲时缩到 0；当 Redis 队列有任务时再拉起 Worker。等月 GPU 使用小时数稳定达到包月盈亏平衡点，再切常驻 GPU。

## 7. 安全边界

SaaS 版必须把人脸与声音素材视为敏感业务数据：

- tenant 级对象存储前缀隔离
- 私有 bucket + 临时签名 URL
- 上传内容类型与大小限制
- 任务 payload 禁止任意本地路径
- Worker 只读取属于当前 tenant/job 的 asset
- 原始人脸/声音设置可配置保留周期
- 删除账号/讲师时清理关联素材
- 管理员审计日志

## 8. 分支策略

`main`：继续保持当前可用的 Mac 本地版。

`feat/saas-cloud`：云端 SaaS 改造开发线。

在 Linux CUDA Worker、数据库 migration、鉴权和核心 API 稳定前，不建议直接合并 `main`。可以先通过 draft PR 持续审查差异。
