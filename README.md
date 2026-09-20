# Mac Digital Human SaaS

面向数字人微课生产的独立 SaaS 产品仓库。该仓库由原 `wudanwt/mac-digital-human` 的 `feat/saas-cloud` 分支拆分而来，现作为 SaaS 控制面、课程工作室和 Mac MLX Worker 的主开发仓库。

## 当前产品能力

- 多租户账号、工作区、成员与权限
- 数字人资产：肖像 / 母版视频 / CosyVoice 2.0 克隆声音
- 透明讲师资产：母版视频一次性人像抠像、Alpha 资产、透明 PNG 预览、白底质检视频
- 课程讲师背景模式：透明叠加 / 纯白背景 / 原始背景，可逐页设置或一键应用全部页面
- 四阶段课程工作室：课件 → 文稿确认 → 画面排版 → 包装与生成
- PPT / PDF 逐页解析、缩略图与讲稿编辑
- 16:9 PPT / 数字人自由拖拽排版、内置演播厅背景与自定义背景
- PostgreSQL + Redis 异步任务系统，Mock / MuseTalk 分队列
- 逐页任务详情：TTS / MuseTalk / Compose 状态、耗时和 ETA
- Apple Silicon Mac MLX Worker + Linux NVIDIA CUDA Remote Worker
- MuseTalk 1.5 MLX 常驻 Runtime、VAE latent / mask 缓存与 batch 自动调优
- CosyVoice 2.0 zero-shot 语音克隆与课程语音流水线
- 字幕、AI 生成标识、MP4 成片预览与下载
- 套餐、额度、对象存储、授权记录、内容举报与运营后台

## 架构

```text
Browser
   |
   v
SaaS API (Docker, :8918)
   |-- PostgreSQL
   |-- Redis
   |-- Private Assets / Object Storage
   |
   +--> avatar:render:mock --------> Docker Mock Worker
   |
   `--> distributed page pool -----+-> Mac Apple Silicon Worker (MLX)
                                  |
                                  `-> Linux NVIDIA Worker (CUDA)
                                      |-- CosyVoice 2.0
                                      |-- MuseTalk 1.5
                                      |-- Portrait Matting / Alpha Assets
                                      `-- FFmpeg / Transparent Course Composer
```

本地 Mac Worker 仍可沿用现有 Redis/共享目录模式；公网 Mac/CUDA Remote Worker 通过 Center HTTPS + Lease 协议领取逐页任务。两种模式并存，不改变现有 Mac 运行路径。

## 快速开始

### 1. 克隆 SaaS 仓库

```bash
git clone https://github.com/wudanwt/mac-digital-human-saas.git
cd mac-digital-human-saas
```

### 2. 准备配置

```bash
cp .env.saas.example .env.saas
```

开发环境默认将 PostgreSQL / Redis 仅暴露到本机，并将 `./workspace`、`./outputs` 与 Mac Worker 共享。

### 3. 启动 SaaS 控制面

```bash
docker compose \
  --env-file .env.saas \
  -f docker-compose.saas.yml \
  up -d --build
```

如需同时运行 Mock Worker：

```bash
docker compose \
  --env-file .env.saas \
  -f docker-compose.saas.yml \
  --profile mock-worker \
  up -d --build
```

打开：

```text
http://127.0.0.1:8918
```

## Mac MLX · MuseTalk Worker

Apple Silicon 首次安装模型与运行环境：

```bash
bash scripts/setup.sh
```

`setup.sh` 会安装 SaaS、MuseTalk、CosyVoice 与人像抠像依赖，并预下载默认的 `birefnet-portrait` 抠像模型。也可以单独执行：

```bash
uv pip install --python .venv/bin/python -e '.[saas,matting]'
.venv/bin/python scripts/setup_matting.py
```

如需切换本地抠像模型：

```bash
export AVATAR_MATTING_MODEL=birefnet-portrait
```

真实 SaaS 生成时，在 Mac 宿主机另开终端：

```bash
bash scripts/saas/start_mlx_worker_mac.sh
```

启动脚本会先检查 Apple Silicon、FFmpeg、PostgreSQL、Redis、共享素材目录、MuseTalk MLX、CosyVoice 与 Portrait Matting，全部通过后才进入 Worker 循环。

详细说明见：[`docs/MAC_MLX_SAAS.md`](docs/MAC_MLX_SAAS.md)。

Linux NVIDIA CUDA Worker 的安装、配置与启动见：[`docs/CUDA_REMOTE_WORKER.md`](docs/CUDA_REMOTE_WORKER.md)。

### 公网 Remote Worker

Page-level distributed Worker 支持 API-only 模式：异地 Mac 只需要主动访问 Center HTTPS，不需要 PostgreSQL、Redis 或对象存储凭据。生产对象存储为 S3 / OSS / COS 时，可开启短时 Signed URL 直下/直传，大文件不再经过 FastAPI；直连失败会自动回退 Center proxy。

Remote Worker V3 支持一次性 Enrollment Code：管理员无需分发长期 Worker Token，目标 Mac 自助换取凭据后写入 macOS Keychain，并可安装 LaunchAgent 自动启动。运营后台可查看 Worker 状态、版本、槽位并执行 Drain / 恢复 / 吊销。

部署与验收步骤见：[`docs/REMOTE_WORKER_INTERNET.md`](docs/REMOTE_WORKER_INTERNET.md)。

群晖 NAS + 双 Mac mini M4 的低成本生产部署架构、域名/HTTPS/MinIO/备份与分阶段上线方案见：[`docs/SYNOLOGY_M4_PRODUCTION_DEPLOYMENT.md`](docs/SYNOLOGY_M4_PRODUCTION_DEPLOYMENT.md)。

## 透明讲师资产工作流

透明抠像发生在数字人资产阶段，而不是每次课程生成时重复执行：

```text
原始母版视频
  -> 一次性 Portrait Matting
  -> Alpha Mask 视频
  -> 透明 PNG 预览
  -> 白底质检视频
  -> 保存为数字人生产资产
```

课程生成时只复用 Alpha：

```text
CosyVoice 语音
  -> MuseTalk 口型视频
  -> 按 MuseTalk 同一 ping-pong 帧序列复用 Alpha
  -> alphamerge
  -> 透明人物叠加到 PPT / 背景
  -> 最终 MP4
```

课程工作室支持三种讲师模式：

- `transparent`：人物背景完全移除，直接透明叠加到课程画面，默认推荐。
- `white`：使用同一套 Alpha，在讲师区域铺纯白背景。
- `original`：保留原始母版视频背景，用于兼容旧课程或特殊场景。

排版预览使用透明 PNG，最终成片使用对应 Alpha 视频；讲师框内统一采用 `center bottom` 底部对齐，避免预览与最终成片上下位置不一致。

如果数字人更换母版视频，原透明资产会自然失效，需要针对新母版重新处理。课程选择透明或白底模式时，如果透明资产尚未完成，Worker 会拒绝生成并给出明确错误，而不会悄悄退化成错误背景。

## 真实课程生成链路

```text
PPT / PDF
  -> 页面解析与渲染
  -> 逐页讲稿
  -> CosyVoice 2.0 克隆语音
  -> MuseTalk 1.5 MLX 数字人口型
  -> 复用预处理 Alpha（透明 / 白底模式）
  -> PPT / 数字人 / 背景排版
  -> 字幕与 AI 标识
  -> FFmpeg 合成
  -> SaaS Output Asset
  -> 在线预览 / 下载
```

## CI

新仓库独立运行：

- Python compile
- Shell syntax
- Browser JavaScript syntax（含透明资产 UI 与讲师模式 UI）
- PostgreSQL Alembic upgrade / downgrade / upgrade
- PostgreSQL + Redis pytest
- MuseTalk ping-pong Alpha 索引回归测试
- 真实 FFmpeg `alphamerge + overlay` 透明合成烟雾测试
- Docker Compose validation
- SaaS API Docker build

## 目录说明

```text
app/saas/                SaaS API、任务、存储、计费、合规与当前 Web UI
app/saas/avatar_matting_* 透明讲师资产模型、API、处理引擎、Worker 与 UI
app/saas/avatar_alpha.py MuseTalk 同步 Alpha 循环复用
app/saas/transparent_composer.py 透明 / 白底讲师最终合成
app/engines/             MuseTalk MLX 引擎与常驻 Runtime
app/tts/                 CosyVoice Provider
app/ppt/                 PPT / PDF 解析与渲染
app/composer.py           课程画面合成
migrations/               PostgreSQL Alembic migrations
scripts/saas/             Mac SaaS Worker 启动脚本
digital-human-tts/        CosyVoice 适配与运行资源
tests/                    自动化测试
docs/                     架构、验收、安全与产品审计文档
```

## 仓库边界

- `wudanwt/mac-digital-human-saas`：从现在开始作为 SaaS 产品主仓库。
- `wudanwt/mac-digital-human`：保留原本地数字人项目及迁移前历史，不再作为 SaaS 日常开发主线。

本次拆仓保留了 `feat/saas-cloud` 的产品/运行代码提交历史。由于 GitHub Actions 的跨仓库 token 不允许迁移 workflow 文件历史，`.github/workflows` 的历史路径在导入时单独剥离，当前 CI workflow 已在新仓库重新建立；这不影响业务源码与运行代码历史。
