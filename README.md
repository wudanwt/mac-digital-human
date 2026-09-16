# Mac Digital Human SaaS

面向数字人微课生产的独立 SaaS 产品仓库。该仓库由原 `wudanwt/mac-digital-human` 的 `feat/saas-cloud` 分支拆分而来，现作为 SaaS 控制面、课程工作室和 Mac MLX Worker 的主开发仓库。

## 当前产品能力

- 多租户账号、工作区、成员与权限
- 数字人资产：肖像 / 母版视频 / CosyVoice 2.0 克隆声音
- 四阶段课程工作室：课件 → 文稿确认 → 画面排版 → 包装与生成
- PPT / PDF 逐页解析、缩略图与讲稿编辑
- 16:9 PPT / 数字人自由拖拽排版、内置演播厅背景与自定义背景
- PostgreSQL + Redis 异步任务系统，Mock / MuseTalk 分队列
- 逐页任务详情：TTS / MuseTalk / Compose 状态、耗时和 ETA
- Apple Silicon Mac 宿主机真实 Worker
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
   `--> avatar:render:musetalk ----> Mac Apple Silicon Worker
                                      |-- CosyVoice 2.0
                                      |-- MuseTalk 1.5 MLX
                                      `-- FFmpeg / Course Composer
```

Docker 控制面与 Mac Worker 通过 Redis 队列和共享素材目录协同。Mock 与 MuseTalk 使用独立队列，不会互相抢任务。

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

真实 SaaS 生成时，在 Mac 宿主机另开终端：

```bash
bash scripts/saas/start_mlx_worker_mac.sh
```

启动脚本会先检查 Apple Silicon、FFmpeg、PostgreSQL、Redis、共享素材目录、MuseTalk MLX 与 CosyVoice 模型，全部通过后才进入 Worker 循环。

详细说明见：[`docs/MAC_MLX_SAAS.md`](docs/MAC_MLX_SAAS.md)。

## 真实课程生成链路

```text
PPT / PDF
  -> 页面解析与渲染
  -> 逐页讲稿
  -> CosyVoice 2.0 克隆语音
  -> MuseTalk 1.5 MLX 数字人口型
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
- Browser JavaScript syntax
- PostgreSQL Alembic upgrade / downgrade / upgrade
- PostgreSQL + Redis pytest
- Docker Compose validation
- SaaS API Docker build

## 目录说明

```text
app/saas/                SaaS API、任务、存储、计费、合规与当前 Web UI
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
