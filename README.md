# mac-digital-human

面向 **Apple Silicon（优先 M5 Pro 48GB）** 的本地数字人工作台。

项目现在采用双引擎架构：

| 模式 | 引擎 | 输入 | 优势 | 推荐用途 |
| --- | --- | --- | --- | --- |
| ⚡ 极速数字人口播 | MuseTalk 1.5 MLX | 母版视频 + 新音频 | 快、身份稳定、适合批量 | 培训正文、课程批量口播 |
| 🎬 高质量数字人 | LongCat-Video-Avatar 1.5 MLX | 参考照片 + 音频 + Prompt | 会生成表情、头动和人物动态 | 课程开场、章节引导、精品短视频 |

> 当前 LongCat MLX 端属于单段高质量 AI2V 生成，不是实时数字人，也还没有在本项目中接入长视频续写。M5 Pro 48GB 默认使用 **Q4 DMD merged**。

## 当前状态

- [x] Apple Silicon 环境检测
- [x] MuseTalk-MLX 快速口型引擎
- [x] LongCat Avatar 1.5 MLX 高质量引擎适配
- [x] M5 Pro 48GB 默认 LongCat Q4 配置
- [x] CLI 双引擎入口
- [x] FastAPI 双引擎 API
- [x] Web 双模式 UI
- [x] 单机串行任务队列，避免统一内存并发争抢
- [x] LongCat 输出自动重新封装原音频
- [x] 模型 / 上游代码固定版本与独立安装脚本
- [ ] 在目标 M5 Pro 48GB 真机完成 LongCat 首个样例验收
- [ ] LongCat 长视频分段 / continuation
- [ ] FasterLivePortrait-MLX 表情增强
- [ ] 声音克隆 / TTS
- [ ] PPT → 讲稿 → TTS → 数字讲师视频
- [ ] 实时 AI Agent 数字专家

## 架构

```text
                         Mac Digital Human
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
          MuseTalk Fast                  LongCat Quality
                 │                             │
     master video + audio          image + audio + prompt
                 │                             │
 face / landmark preprocessing        Avatar 1.5 MLX Q4
                 │                             │
        MLX lip-sync core              full video generation
                 │                             │
          blend + mux                    mux original audio
                 └──────────────┬──────────────┘
                                │
                       outputs/<job>/result.mp4
                                │
                    CLI / Web UI / FastAPI
```

任务默认串行执行。MuseTalk 上游会使用共享临时目录，而 LongCat 在 48GB 统一内存机器上本身也很重，因此不建议两个生成任务并发跑。

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
```

### 2. 安装 MuseTalk 快速引擎

```bash
bash scripts/setup.sh
```

脚本会建立 `.venv`、安装 FFmpeg / uv 依赖、固定克隆 MuseTalk-MLX 与 MuseTalk，并下载 MuseTalk Q8 及人脸预处理模型。

### 3. 安装 LongCat 高质量引擎

```bash
bash scripts/setup_longcat.sh
```

默认下载：

```text
mlx-community/LongCat-Video-Avatar-1.5-q4-dmd-merged
```

模型体积约为几十 GB 级，请预留足够磁盘空间。模型、上游仓库、人物素材和生成结果都默认不提交到 Git。

也可以一次安装两套：

```bash
WITH_LONGCAT=1 bash scripts/setup.sh
```

### 4. 检查运行环境

```bash
.venv/bin/python scripts/check_runtime.py --engine all
```

只检查 LongCat：

```bash
.venv/bin/python scripts/check_runtime.py \
  --engine longcat \
  --longcat-variant q4-merged
```

## Web UI

```bash
bash scripts/run_web.sh
```

浏览器打开：

```text
http://127.0.0.1:8000
```

页面中可以直接切换：

- **极速数字人口播**：上传母版视频 + 音频。
- **高质量数字人**：上传参考照片 + 音频 + Prompt。

Web 服务默认只监听本机。只有明确需要局域网访问时才建议设置 `HOST=0.0.0.0`。

## CLI

### MuseTalk

```bash
bash scripts/run_avatar.sh \
  --engine musetalk \
  --video samples/master.mp4 \
  --audio samples/voice.wav \
  --variant q8
```

`--engine` 省略时仍默认 MuseTalk，兼容旧命令：

```bash
bash scripts/run_avatar.sh \
  --video samples/master.mp4 \
  --audio samples/voice.wav
```

### LongCat

```bash
bash scripts/run_avatar.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --prompt "A professional Chinese male instructor speaking naturally to camera, subtle head movement, natural hand gestures, calm confident expression."
```

常用 LongCat 参数：

```text
--variant q4-merged   # M5 Pro 48GB 默认推荐
--width 832
--height 480
--num-frames 93      # 必须满足 4n+1
--seed 42
```

快速测试可以用：

```text
--width 768 --height 432 --num-frames 61
```

## API

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

### MuseTalk 任务

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F "engine=musetalk" \
  -F "video=@samples/master.mp4" \
  -F "audio=@samples/voice.wav" \
  -F "variant=q8"
```

### LongCat 任务

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F "engine=longcat" \
  -F "image=@samples/ref.png" \
  -F "audio=@samples/voice.wav" \
  -F "variant=q4-merged" \
  -F "prompt=A professional Chinese male instructor speaking naturally to camera" \
  -F "longcat_size=480x832" \
  -F "num_frames=93"
```

最终视频统一位于：

```text
outputs/<job-id>/result.mp4
```

运行日志位于：

```text
workspace/<job-id>/render.log
```

## LongCat 当前限制

当前接入基于 `xocialize/longcat-avatar-mlx` 的 AI2V v1 路线：

1. 一次任务生成一个短视频片段。
2. 还没有接入 LongCat 官方的多段 continuation / 长视频拼接。
3. 不是实时引擎；生成速度显著慢于 MuseTalk。
4. 48GB 机器应优先 Q4；Q8 可实验，BF16 不建议作为默认。
5. 首次运行会加载大模型，等待时间和内存峰值都明显高于 MuseTalk。

因此当前推荐工作流是：

```text
培训正文 / 批量课程  -> MuseTalk
课程开场 / 宣传短片 -> LongCat
```

## 素材建议

### MuseTalk 母版

- 1080p / 25fps 优先
- 正脸或轻微侧脸
- 胸部以上固定机位
- 光照稳定
- 嘴部无遮挡
- 30–60 秒自然呼吸和轻微动作

### LongCat 参考照片

- 单人清晰正面或轻微侧面
- 面部无遮挡
- 尽量保持肩部 / 上半身信息完整
- 光线自然
- 不建议极端广角或复杂遮挡

人物照片、声音、模型和生成文件默认被 `.gitignore` 排除。

## 目录

```text
app/
  engines/
    base.py             # 共享结果 / 错误类型
    musetalk.py         # 快速口型引擎
    longcat.py          # 高质量数字人引擎
  cli.py
  jobs.py
  main.py
scripts/
  setup.sh
  setup_longcat.sh
  setup_models.py
  setup_longcat_models.py
  longcat_infer.py
  check_runtime.py
vendor/                 # 上游仓库，不入 Git
models/                 # 模型权重，不入 Git
workspace/              # 中间文件，不入 Git
outputs/                 # 最终视频，不入 Git
samples/                 # 本地人物素材，不入 Git（保留 README）
docs/
tests/
```

## 上游与固定版本

当前安装脚本固定：

- `xocialize/musetalk-mlx`：Apple MLX MuseTalk 1.5 移植
- `jjt997/musetalk`：MuseTalk 视频预处理 / blending 工具
- `xocialize/longcat-avatar-mlx`：Apple MLX LongCat-Video-Avatar-1.5 移植
- LongCat 官方模型来源：`meituan-longcat/LongCat-Video`

本仓库只维护本地编排和适配，不重新发布上游模型权重。各模型、代码和依赖的许可证需分别遵守。

## 下一阶段

下一步重点不是继续堆模型，而是把生成流程产品化：

1. M5 Pro 48GB 真机首跑与性能记录。
2. LongCat 参考照片模板 / Prompt 预设。
3. 课程脚本 → TTS → 数字人批量任务。
4. LongCat 精品片段 + MuseTalk 正文自动混剪。
5. 再评估 FasterLivePortrait 与实时 Agent。

详见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。
