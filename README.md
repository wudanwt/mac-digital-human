# mac-digital-human

面向 **Apple Silicon（优先 M5 Pro 48GB）** 的本地数字人生产工作台。

项目不再只解决“让一个头像说话”，而是把生成流程拆成三个可组合层：

| 层 | 组件 | 作用 |
| --- | --- | --- |
| ⚡ 快速数字人口播 | MuseTalk 1.5 MLX | 母版视频 + 音频，适合课程正文和批量口播 |
| 🎬 高质量数字人 | LongCat-Video-Avatar 1.5 MLX | 照片 + 音频 + Prompt，适合片头、章节引导、精品短段 |
| 🔊 本地 TTS | MLX-Audio + Qwen3-TTS | 中文预设音色或参考音频声音克隆 |

在此之上提供 **人物 Profile、Prompt 预设、课程 Manifest、自动引擎选择、FFmpeg 成片拼接和真机 benchmark**。

## 当前能力

- [x] MuseTalk-MLX 快速口型引擎
- [x] LongCat Avatar 1.5 MLX Q4 高质量引擎
- [x] Web / CLI / FastAPI 双引擎入口
- [x] 本地人物 Profile：照片、MuseTalk 母版、Prompt、TTS 参考统一复用
- [x] 能源培训 / 高管简报 / 电力市场专家等 Prompt 预设
- [x] MLX-Audio + Qwen3-TTS 中文 TTS
- [x] Qwen3-TTS 参考音频零样本声音克隆接口
- [x] Course Manifest：脚本 → TTS → 数字人批量生成
- [x] `hero/intro/section` 自动优先 LongCat，`body` 自动走 MuseTalk
- [x] LongCat 自动模式超长时回退 MuseTalk
- [x] LongCat + MuseTalk 片段统一规格并自动混剪
- [x] M5 真机 benchmark 记录器
- [x] GitHub CI：compile + unit tests
- [ ] M5 Pro 48GB LongCat Q4 首个真实 benchmark 数据
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
          MLX-Audio / Qwen3-TTS         │
                     │                   │
                   audio                 │
                     │                   │
             ┌───────┴────────┐          │
             │                │          │
        hero / section       body        │
             │                │          │
             ↓                ↓          │
       LongCat MLX       MuseTalk MLX ←──┘
             │                │
             └───────┬────────┘
                     ↓
              generated clips
                     ↓
             FFmpeg normalize
                     ↓
              final course.mp4
```

针对 M5 Pro 48GB，TTS 和 LongCat **不同时驻留**：课程流水线先一次性生成所有配音并释放 TTS，再开始视频生成，降低统一内存压力。

## 快速开始

### 1. 克隆

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
```

### 2. 安装

只需要 MuseTalk：

```bash
bash scripts/setup.sh
```

LongCat：

```bash
bash scripts/setup_longcat.sh
```

TTS：

```bash
bash scripts/setup_tts.sh
```

一次装完整课程生产栈：

```bash
WITH_LONGCAT=1 WITH_TTS=1 bash scripts/setup.sh
```

M5 Pro 48GB 的 LongCat 默认是：

```text
mlx-community/LongCat-Video-Avatar-1.5-q4-dmd-merged
```

TTS 默认是：

```text
mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit
```

如需把声音克隆模型也提前缓存：

```bash
WITH_CLONE_MODEL=1 bash scripts/setup_tts.sh
```

## 单段 Web 工作台

```bash
bash scripts/run_web.sh
```

打开：

```text
http://127.0.0.1:8000
```

页面可以：

- 选择 MuseTalk / LongCat。
- 选择本地人物 Profile。
- 选择 LongCat Prompt 预设。
- 继续手工修改 Prompt。
- Profile 已配置照片 / 母版时无需重复上传。

服务默认只监听 `127.0.0.1`。

## 人物 Profile

复制：

```bash
cp profiles/profile.example.json profiles/dan.json
```

示例：

```json
{
  "id": "dan",
  "name": "丹哥｜能源培训讲师",
  "image": "../samples/ref.png",
  "master_video": "../samples/master.mp4",
  "prompt_preset": "energy_training_studio",
  "tts": {
    "voice": "Dylan",
    "ref_audio": "../samples/voice-reference.wav",
    "ref_text": "这里填写参考音频准确逐字稿"
  }
}
```

设置 `ref_audio + ref_text` 后，课程流水线会使用 Qwen3-TTS Base 做声音克隆；不设置则使用 CustomVoice 预设中文音色。

`profiles/*.json`（除示例）、照片、视频和声音默认都被 `.gitignore` 排除。

## LongCat Prompt 预设

内置：

```text
energy_training_studio  能源科技培训演播室
executive_briefing      高管汇报 / 正式简报
power_market_lab        电力市场数字专家
warm_classroom          亲和课堂
neutral_closeup         中性稳定近景
```

这些预设不仅是 Prompt，还带推荐的分辨率和帧数。

## 单段 CLI

### MuseTalk

```bash
bash scripts/run_avatar.sh \
  --engine musetalk \
  --video samples/master.mp4 \
  --audio samples/voice.wav \
  --variant q8
```

### LongCat

```bash
bash scripts/run_avatar.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --width 768 \
  --height 432 \
  --num-frames 61 \
  --prompt "A professional Chinese male instructor speaking naturally to camera."
```

首跑先用 `768×432 / 61f`，稳定后再测试 `832×480 / 93f`。

## 课程自动生产

参考：

```text
examples/course.example.json
```

基本结构：

```json
{
  "title": "能源市场化业务示例课程",
  "profile": "dan",
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
hero / intro / section  -> LongCat
body                    -> MuseTalk
```

LongCat 当前仍适合短段。`auto` 模式下，如果配音长度超过当前 LongCat 帧数上限，会自动切回 MuseTalk，并把原因写入报告。

输出：

```text
outputs/courses/<course-id>/course.mp4
workspace/courses/<course-id>/course-report.json
```

完整说明见 [`docs/COURSE_PIPELINE.md`](docs/COURSE_PIPELINE.md)。

## M5 Pro 48GB 真机 Benchmark

首个 LongCat 测试：

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

报告会记录：

- 芯片 / 内存
- 总耗时
- 输出视频时长
- realtime factor
- 进程树峰值 RSS
- 推理期间最低可用内存
- variant / 尺寸 / 帧数 / seed

详见 [`docs/BENCHMARK.md`](docs/BENCHMARK.md)。

## 输出目录

```text
outputs/<job-id>/result.mp4
outputs/courses/<course-id>/course.mp4
```

中间文件和日志：

```text
workspace/<job-id>/
workspace/courses/<course-id>/
```

## 目录结构

```text
app/
  engines/             MuseTalk / LongCat 适配
  tts/                 MLX-Audio TTS 适配
  presets.py           Prompt + Avatar Profile
  course.py            课程编排
  composer.py          FFmpeg 成片
  jobs.py              单机任务队列
  main.py              Web / API
scripts/
  setup.sh
  setup_longcat.sh
  setup_tts.sh
  run_avatar.sh
  run_course.sh
  run_benchmark.sh
  benchmark.py
  longcat_infer.py
profiles/               本机人物模板
examples/               课程 Manifest 示例
docs/
benchmarks/local/       真机报告（不入 Git）
```

## 上游

当前主链依赖：

- `xocialize/musetalk-mlx`
- `jjt997/musetalk`
- `xocialize/longcat-avatar-mlx`
- `meituan-longcat/LongCat-Video`
- `Blaizzy/mlx-audio`
- `mlx-community/Qwen3-TTS-*`

安装脚本对关键上游代码使用固定 commit，避免上游突然变化破坏本地环境。本仓库不重新发布模型权重；各组件继续遵守各自许可证。

## 下一步

不继续堆模型，优先做：

1. 在 M5 Pro 48GB 跑出 LongCat 61f / 93f benchmark。
2. 建真实人物 Profile，验证照片、母版和声音参考长期复用。
3. 用真实 4~6 段课程跑通自动生产。
4. 根据成片质量决定下一优先级是字幕、PPT 合成还是母版缓存。
5. FasterLivePortrait 与实时 Agent 暂时保持评估状态。

详见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。
