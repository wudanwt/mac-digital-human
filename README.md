# mac-digital-human

面向 **Apple Silicon（优先 M5 Pro 48GB）** 的本地数字人生产工作台。

项目把课程生成拆成四个可组合层：

| 层 | 组件 | 作用 |
| --- | --- | --- |
| ⚡ 快速数字人口播 | MuseTalk 1.5 MLX | 母版视频 + 音频，适合课程正文和批量口播 |
| 🎬 高质量数字人 | LongCat-Video-Avatar 1.5 MLX | 照片 + 音频 + Prompt，适合片头、章节引导、精品短段 |
| 🔊 生产型 TTS | Audio8 0.1B INT8 ONNX | CPU 常驻、低内存、批量课程、零样本音色注册 |
| 🎙️ 精品 TTS | MLX-Audio + Qwen3-TTS | 情绪 / 指令控制、高表达配音 |

在此之上提供 **人物 Profile、Prompt 预设、课程 Manifest、自动引擎选择、FFmpeg 成片拼接和真机 benchmark**。

## 当前能力

- [x] MuseTalk-MLX 快速口型引擎
- [x] LongCat Avatar 1.5 MLX Q4 高质量引擎
- [x] Web / CLI / FastAPI 双视频引擎入口
- [x] Audio8 0.1B INT8 ONNX CPU TTS，默认生产 Provider
- [x] Audio8 本地 HTTP 常驻服务 / 自动启动 / 音色注册
- [x] Qwen3-TTS MLX 精品配音与零样本声音克隆
- [x] 本地人物 Profile：照片、MuseTalk 母版、Prompt、TTS 声音统一复用
- [x] 能源培训 / 高管简报 / 电力市场专家等 Prompt 预设
- [x] Course Manifest：脚本 → TTS → 数字人批量生成
- [x] `hero/intro/section` 自动优先 LongCat，`body` 自动走 MuseTalk
- [x] LongCat 自动模式超长时回退 MuseTalk
- [x] LongCat + MuseTalk 片段统一规格并自动混剪
- [x] M5 真机 benchmark 记录器
- [x] GitHub CI：compile + unit tests
- [ ] M5 Pro 48GB LongCat Q4 首个真实 benchmark 数据
- [ ] M5 Pro Audio8 实测 RTF / RSS 数据
- [ ] PPT 页面合成 / 自动字幕
- [ ] LongCat continuation
- [ ] FasterLivePortrait / 实时 Agent 评估

## 整体架构

```text
                         Course Manifest
                               │
                     ┌─────────┴─────────┐
                     │                   │
                 script text         Avatar Profile
                     │           image / master / prompt
                     ↓                   │
             TTS Provider Registry       │
               │             │           │
          Audio8 ONNX      Qwen3 MLX     │
          CPU default      premium       │
               └──────┬──────┘           │
                      ↓                   │
                    audio                 │
                      │                   │
             ┌────────┴────────┐          │
             │                 │          │
        hero / section        body        │
             ↓                 ↓          │
       LongCat MLX        MuseTalk MLX ←──┘
             │                 │
             └────────┬────────┘
                      ↓
               generated clips
                      ↓
              FFmpeg normalize
                      ↓
               final course.mp4
```

Audio8 运行在**隔离的 CPU ONNX venv + 本机服务**里，不与 LongCat/MuseTalk 的 MLX 环境混装。Qwen3 仍在主 MLX 环境中，只有明确需要高表达时才启用。

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
```

### 2. 安装视频引擎

MuseTalk：

```bash
bash scripts/setup.sh
```

LongCat：

```bash
bash scripts/setup_longcat.sh
```

### 3. 安装 TTS

默认生产型 Audio8：

```bash
bash scripts/setup_tts.sh
```

等价于：

```bash
bash scripts/setup_audio8.sh
```

只安装 Qwen3：

```bash
TTS_PROVIDER=qwen3 bash scripts/setup_tts.sh
```

两套都装：

```bash
TTS_PROVIDER=both bash scripts/setup_tts.sh
```

一次装完整课程生产栈：

```bash
WITH_LONGCAT=1 WITH_TTS=1 bash scripts/setup.sh
```

完整双 TTS：

```bash
WITH_LONGCAT=1 WITH_TTS=1 TTS_PROVIDER=both bash scripts/setup.sh
```

## Audio8 运行方式

Audio8 当前固定使用：

```text
Edge0-AI/Audio8_TTS
Audio8/audio8-TTS-0.1B-ONNX-INT8
```

服务默认：

```text
http://127.0.0.1:8024
```

手工启停：

```bash
bash scripts/start_audio8.sh
bash scripts/stop_audio8.sh
```

检查：

```bash
.venv/bin/python scripts/check_tts.py --provider audio8
```

课程流水线会自动启动本地 Audio8 服务，通常不需要手工先启动。

## 人物 Profile

复制：

```bash
cp profiles/profile.example.json profiles/dan.json
```

使用 Audio8 官方默认音色：

```json
{
  "id": "dan",
  "name": "丹哥｜能源培训讲师",
  "image": "../samples/ref.png",
  "master_video": "../samples/master.mp4",
  "prompt_preset": "energy_training_studio",
  "tts": {
    "provider": "audio8",
    "voice": "default",
    "threads": 5
  }
}
```

### Audio8 声音克隆

可以先显式注册：

```bash
.venv/bin/python scripts/register_audio8_voice.py \
  --name dan \
  --audio samples/voice-reference.wav \
  --text "这里填写参考音频准确逐字稿"
```

之后 Profile 只需要：

```json
{
  "tts": {
    "provider": "audio8",
    "voice": "dan"
  }
}
```

也可以直接在 Profile 中提供 `ref_audio + ref_text`，第一次课程运行时自动注册。

### Qwen3 精品配音

```json
{
  "tts": {
    "provider": "qwen3",
    "voice": "Dylan",
    "language": "Chinese",
    "instruct": "专业、自然、清晰，有交流感。"
  }
}
```

旧 Manifest 如果没有 `provider`，但明确写了 `mlx-community/Qwen3-TTS-*` 模型，仍会自动识别为 Qwen3，不破坏旧配置。

详见 [`docs/TTS.md`](docs/TTS.md) 与 [`profiles/README.md`](profiles/README.md)。

## 单段 Web 工作台

```bash
bash scripts/run_web.sh
```

打开：

```text
http://127.0.0.1:8000
```

页面可以选择 MuseTalk / LongCat、人物 Profile 和 LongCat Prompt 预设。单段工作台仍使用你上传或外部生成的音频；课程 TTS 由 Course Pipeline 负责。

## 课程自动生产

参考：

```text
examples/course.example.json
```

最小结构：

```json
{
  "title": "能源市场化业务示例课程",
  "profile": "dan",
  "tts": {
    "provider": "audio8",
    "voice": "dan"
  },
  "segments": [
    {
      "id": "opening",
      "role": "hero",
      "engine": "auto",
      "script": "欢迎来到本次课程。"
    },
    {
      "id": "body-1",
      "role": "body",
      "engine": "auto",
      "script": "这里进入课程正文。"
    }
  ]
}
```

运行：

```bash
bash scripts/run_course.sh examples/course.example.json
```

自动策略：

```text
TTS 默认             -> Audio8 ONNX
TTS 精品指定         -> Qwen3 MLX
hero / intro / section -> LongCat
body                   -> MuseTalk
```

输出：

```text
outputs/courses/<course-id>/course.mp4
workspace/courses/<course-id>/course-report.json
```

报告会记录课程实际使用的 `tts_provider` 和每一段实际使用的数字人引擎。

完整说明见 [`docs/COURSE_PIPELINE.md`](docs/COURSE_PIPELINE.md)。

## LongCat 首跑 Benchmark

```bash
bash scripts/run_benchmark.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --width 768 \
  --height 432 \
  --num-frames 61 \
  --label m5-pro-48g-first-run
```

详见 [`docs/BENCHMARK.md`](docs/BENCHMARK.md)。

## 目录结构

```text
app/
  engines/              MuseTalk / LongCat
  tts/
    base.py             Provider contract
    registry.py         Provider selection
    audio8_onnx.py      Audio8 CPU ONNX adapter
    mlx_audio.py        Qwen3 MLX adapter
  presets.py            Prompt + Avatar Profile
  course.py             课程编排
  composer.py           FFmpeg 成片
scripts/
  setup_audio8.sh
  setup_qwen3_tts.sh
  setup_tts.sh
  start_audio8.sh
  stop_audio8.sh
  register_audio8_voice.py
  check_tts.py
  run_course.sh
profiles/
examples/
docs/
benchmarks/local/       真机报告（不入 Git）
```

## 上游

当前主链依赖：

- `xocialize/musetalk-mlx`
- `jjt997/musetalk`
- `xocialize/longcat-avatar-mlx`
- `meituan-longcat/LongCat-Video`
- `Edge0-AI/Audio8_TTS`
- `Audio8/audio8-TTS-0.1B-ONNX-INT8`
- `Blaizzy/mlx-audio`
- `mlx-community/Qwen3-TTS-*`

安装脚本对关键上游代码使用固定 commit。本仓库不重新发布模型权重；代码和模型权重的许可证需分别遵守。

## 下一步

1. 在 M5 Pro 48GB 跑出 LongCat 61f / 93f benchmark。
2. 跑 Audio8 的真实中文课程 TTS，记录 RTF、RSS 和克隆音色主观质量。
3. 建真实 `dan` Profile，固定声音、照片与母版。
4. 用真实 4~6 段课程跑通 Audio8 → LongCat/MuseTalk → 自动混剪。
5. 然后优先评估 PPT 页面合成 / 自动字幕，不急着继续堆模型。
