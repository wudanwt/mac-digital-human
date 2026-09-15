# Digital Human SaaS 云端版

> 开发分支：`feat/saas-cloud`
>
> 本分支把原来的 Apple Silicon 单机数字人微课工作台拆成独立的多租户 SaaS 控制面。Mac 本地版继续留在 `main`，两条运行路径互不绑死。

## 1. 当前已完成的 SaaS 产品能力

### 用户与工作区

- 邮箱注册 / 登录
- scrypt 密码哈希
- JWT Access Token
- 多工作区切换
- Owner / Admin / Member 权限
- 成员添加 / 移除
- tenant 级数据隔离
- 超级管理员运营权限

### 素材中心

- PPT / 文档 / 图片 / 视频 / 音频上传
- 上传大小限制与扩展名校验
- tenant 隔离的对象 key
- 本地对象存储开发模式
- S3-compatible 私有对象存储
- 临时签名下载 URL
- Worker 素材 materialize
- 素材删除

### 数字人资产

- 数字人 Profile
- 图片人物资产
- MuseTalk 母版视频资产
- 默认克隆音色
- Prompt / 人设描述
- CosyVoice 声音 Profile
- 参考录音与逐字稿

### 课程工作台

- 新建课程
- PPT 关联
- 数字人关联
- 音色关联
- 按页讲稿 JSON
- 每页版式 / 自定义画布参数
- 课程生成提交
- 生成任务历史
- 任务取消
- 进度 / stage / error / output 状态

### 队列与 Worker

- InMemory 开发队列
- Redis 跨机器任务队列
- CPU API 与计算 Worker 分离
- Mock Worker：无 GPU 即可完整测试 SaaS 流程
- Local MLX Worker：Mac 上可跑完整数字人课程生产
- Worker 自动同步数据库状态
- 失败自动退款分钟额度
- 输出自动上传对象存储
- GPU seconds / video seconds 字段已预留

Mac 本地完整课程 Worker 已串联：

```text
PPT
 -> 页面解析 / 渲染
 -> 每页讲稿
 -> CosyVoice TTS
 -> MuseTalk MLX
 -> PPT + 数字人排版
 -> FFmpeg concat
 -> SRT subtitle track
 -> MP4
 -> Object Storage
```

Linux CUDA Worker 与 SaaS 控制面使用相同 `RenderHandler` 契约；CUDA 环境单独部署，避免把数 GB 的 AI 运行环境塞进常驻 API 容器。

### 套餐与用量

默认套餐：

| 套餐 | 月生成额度 | 存储 | 数字人 | 成员 | 默认价 |
|---|---:|---:|---:|---:|---:|
| 体验版 | 30 分钟 | 2 GB | 1 | 1 | ¥0 |
| 专业版 | 600 分钟 | 50 GB | 5 | 3 | ¥199 |
| 企业版 | 3000 分钟 | 500 GB | 30 | 20 | ¥699 |

已实现：

- Subscription
- 剩余秒数
- 任务提交预留额度
- 失败 / 取消自动退款
- Usage Ledger
- 人工额度调整
- Payment Order
- 手工订单确认
- Development Mock Payment
- 微信 / 支付宝 provider 位已预留

微信支付 / 支付宝真实收款需要商户号、证书、回调域名等外部凭据，因此代码中不会伪造真实支付凭据。拿到商户配置后只需接 provider adapter，不影响 SaaS 核心模型。

### 运营后台

- 平台用户数
- 工作区数量
- 排队 / 运行 / 失败任务
- 待支付订单
- 用户启停
- 工作区套餐和剩余额度
- 人工增减分钟数
- 手工订单确认收款
- Audit Log

### Web SaaS 界面

`/` 是独立 SaaS 工作台，不再复用 Mac 单机页面。

包含：

- 登录 / 注册
- 总览
- 课程
- 数字人 / 克隆音色
- 素材中心
- 生成任务
- 套餐 / 用量 / 订单
- 工作区成员设置
- 超级管理员运营页

## 2. 云端架构

```text
Browser
   |
   v
FastAPI SaaS API  (CPU 常驻)
   |
   +---- PostgreSQL
   |       users / tenants / membership
   |       assets / avatars / voices / courses
   |       jobs / subscriptions / usage / orders / audit
   |
   +---- Redis
   |       render queue / shared status / rate-limit
   |
   +---- Object Storage
   |       PPT / image / video / audio / output
   |
   v
Render Queue
   |
   +---- Mock Worker        无 GPU 联调
   +---- MLX Worker         Mac 开发 / 回归
   +---- CUDA Worker        Linux NVIDIA 生产
   `---- Premium Worker     LongCat 等后续精品引擎
```

## 3. 本机无 GPU 启动完整 SaaS

```bash
cp .env.saas.example .env.saas
```

开发测试时 `.env.saas` 使用：

```text
WORKER_BACKEND=redis
SAAS_RENDERER=mock
```

启动 API + PostgreSQL + Redis：

```bash
docker compose -f docker-compose.saas.yml up --build
```

如果希望连 Mock Worker 一起启动：

```bash
docker compose -f docker-compose.saas.yml --profile mock-worker up --build
```

浏览器：

```text
http://127.0.0.1:8918
```

API 文档：

```text
http://127.0.0.1:8918/docs
```

## 4. Mac 上运行真实 MLX Worker

API / PostgreSQL / Redis 可以跑 Docker，Worker 直接在 Mac Host 跑：

```bash
export DATABASE_URL='postgresql+psycopg://digital_human:digital_human@127.0.0.1:5432/digital_human'
export REDIS_URL='redis://127.0.0.1:6379/0'
export WORKER_BACKEND=redis
export SAAS_RENDERER=mlx-local
python -m app.saas.worker
```

要求原本的 MuseTalk-MLX / CosyVoice 环境已经就绪。

## 5. 国内 CUDA 临时机器

仓库已经提供：

```bash
bash scripts/cloud/setup_musetalk_cuda.sh
bash scripts/cloud/check_musetalk_cuda.sh
```

推荐先用 RTX 3090 24GB 做兼容性测试，再用 RTX 4090 24GB 做单位成本 benchmark。

CUDA 真机验证与 SaaS 功能开发是解耦的：即使没有 NVIDIA 机器，注册、登录、素材、数字人、课程、任务、套餐、额度、后台、对象存储、Redis 队列都可以完整开发和验收。

## 6. 数据库

开发环境可以使用 SQLite；Docker / 生产使用 PostgreSQL。

初始化：

```bash
python -m app.saas.bootstrap
```

Alembic：

```bash
alembic upgrade head
```

`app.saas.bootstrap` 也会确保初始表和默认套餐存在，因此新环境可以直接启动。

## 7. API 主要资源

```text
POST /api/saas/auth/register
POST /api/saas/auth/login
GET  /api/saas/auth/me
POST /api/saas/auth/switch-workspace/{tenant_id}

GET/POST /api/saas/workspaces
GET/POST /api/saas/workspaces/members

GET/POST/DELETE /api/saas/assets
GET/POST/DELETE /api/saas/voices
GET/POST/DELETE /api/saas/avatars
GET/POST/PATCH/DELETE /api/saas/courses
POST /api/saas/courses/{id}/render
GET/POST /api/saas/jobs

GET  /api/saas/billing/plans
GET  /api/saas/billing/subscription
GET/POST /api/saas/billing/orders

GET  /api/saas/admin/overview
GET  /api/saas/admin/users
GET  /api/saas/admin/tenants
POST /api/saas/admin/credits
GET  /api/saas/admin/orders
POST /api/saas/admin/orders/{id}/mark-paid
GET  /api/saas/admin/audit
```

## 8. 安全边界

已经实现 / 强制：

- JWT 登录身份
- tenant membership 校验
- 资源查询 tenant filter
- 私有对象存储设计
- S3 signed URL
- 上传体积限制
- 文件扩展名限制
- Rate Limit
- Security headers
- Production JWT secret 校验
- Production 禁止 SQLite
- Production 强制 Redis Worker
- 审计日志

上线时仍必须由部署环境提供：

- HTTPS / TLS
- 域名
- 强随机 `SAAS_JWT_SECRET`
- PostgreSQL 密码 / Redis ACL
- OSS/COS/S3 Access Key Secret
- 备份策略
- WAF / CDN（按业务需要）

## 9. 分支策略

- `main`：当前 Mac 本地生产版
- `feat/saas-cloud`：SaaS 产品开发 / 云端部署版

CUDA 真机 benchmark 完成、生产对象存储与支付商户凭据配置完成之前，不建议把 SaaS 云部署逻辑强行并回 Mac 本地运行路径。
