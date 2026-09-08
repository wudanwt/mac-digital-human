# mac-digital-human

面向 **Apple Silicon（优先 M5 Pro 48GB）** 的本地数字人项目。

第一阶段目标：

> 母版视频 + 新音频 → 自动完成口型同步 → 输出 MP4。

项目优先使用 **MuseTalk 1.5 的 MLX 移植版**完成核心神经网络推理；视频人脸检测、关键点和融合等外围步骤使用 CPU / PyTorch 工具。这样可以避免 CUDA 依赖，同时尽量保留 MuseTalk 1.5 的口型质量。

## 当前状态

- [x] Apple Silicon 环境检测
- [x] 一键安装脚本骨架
- [x] MuseTalk-MLX 引擎适配层
- [x] CLI：视频 + 音频 → 数字人口播
- [x] FastAPI 服务
- [x] 简单 Web UI
- [x] 任务目录与输出管理
- [ ] 在目标 M5 Pro 48GB 真机上完成首个样例验收
- [ ] FasterLivePortrait-MLX 表情 / 头动增强
- [ ] 声音克隆
- [ ] PPT → 讲稿 → TTS → 数字讲师视频
- [ ] 实时 AI Agent 数字专家

## 架构

```text
master video ─┐
              ├─> preprocess face/landmarks ─> MuseTalk-MLX ─> blend/mux ─> output.mp4
new audio ────┘

                                  ┌─ CLI
                                  ├─ Web UI
                                  └─ FastAPI
```

## 为什么不是“纯 MLX”

MuseTalk-MLX 已将 UNet、VAE 和 Whisper 音频编码核心迁移到 Apple MLX，但完整视频流水线仍需要人脸框、DWPose 关键点和 face parsing / blending。第一版因此采用：

- **MLX / Metal**：主要神经网络推理
- **CPU / PyTorch**：S3FD 人脸检测、部分传统预处理与融合
- **ONNX Runtime**：DWPose
- **FFmpeg**：视频标准化与音视频封装

这比强行运行 CUDA 原版更适合 Mac。

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
```

### 2. 检查机器

```bash
python3 scripts/check_env.py
```

### 3. 安装

```bash
bash scripts/setup.sh
```

安装脚本会：

1. 检查 Apple Silicon / macOS。
2. 安装或检查 `ffmpeg`、`git`、`uv`。
3. 建立 `.venv`。
4. 安装本项目依赖。
5. 克隆固定上游：`xocialize/musetalk-mlx` 与 `jjt997/musetalk`。
6. 安装 MuseTalk-MLX 及 Mac 预处理依赖。
7. 下载 Q8 MLX 权重与外围模型。

> 模型文件较大，不提交进 Git 仓库，统一放在 `vendor/` / Hugging Face cache / `models/`。

### 4. 准备素材

建议母版视频：

- 1080p，25 fps 优先
- 正脸或轻微侧脸
- 胸部以上固定机位
- 光照稳定
- 嘴部无遮挡
- 30~60 秒自然说话/轻微动作即可

音频建议：WAV，16 kHz 或更高；程序会自动规范化。

### 5. CLI 生成

```bash
./scripts/run_avatar.sh \
  --video samples/master.mp4 \
  --audio samples/voice.wav
```

默认输出到：

```text
outputs/<job-id>/result.mp4
```

可选参数：

```bash
./scripts/run_avatar.sh --video a.mp4 --audio b.wav --variant q8 --output outputs/demo.mp4
```

M5 Pro 48GB 建议先用 `q8`，稳定后可试 `fp16`。

## Web UI

```bash
./scripts/run_web.sh
```

浏览器打开：

```text
http://127.0.0.1:8000
```

上传母版视频和音频即可创建任务。

## API

启动：

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

创建任务：

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F "video=@samples/master.mp4" \
  -F "audio=@samples/voice.wav" \
  -F "variant=q8"
```

## 目录

```text
app/                    Web/API 与任务编排
scripts/                安装、环境检测、运行脚本
vendor/                 上游仓库（安装时创建，不入 Git）
models/                 本地外围权重（不入 Git）
workspace/              每个任务的中间文件
outputs/                 最终视频
samples/                 用户测试素材（默认不提交大文件）
docs/                    使用说明、录制规范、路线图
```

## 上游

- MuseTalk：`jjt997/musetalk`（实际来源为 Tencent Music Lyra Lab 的 MuseTalk 项目镜像/仓库）
- MuseTalk-MLX：`xocialize/musetalk-mlx`
- FasterLivePortrait-MLX（下一阶段）：`ivanfioravanti/fasterliveportrait-mlx`

本仓库不会重新发布上游模型权重。各模型、权重和依赖继续遵守各自许可证；商业使用前请分别核对。

## M5 Pro 48GB 推荐配置

第一轮：

```text
variant: q8
batch-size: 8（上游默认）
input: 1080p / 25fps
母版长度: 30~60s
```

先以“稳定跑通 + 口型自然”为目标，再逐步增加全身动作和声音克隆。

## Roadmap

详见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。
