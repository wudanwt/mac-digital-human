# 课程批量生产流水线

目标：把“脚本 → TTS → 数字人片段 → 自动混剪”变成一次命令，而不是逐段手工操作。

## 1. 安装完整生产组件

```bash
WITH_LONGCAT=1 WITH_TTS=1 bash scripts/setup.sh
```

默认 TTS 会安装 **Audio8 0.1B INT8 ONNX**。它运行在独立 CPU venv 中，并通过本机 `127.0.0.1:8024` 服务提供合成与音色注册。

也可以分别安装：

```bash
bash scripts/setup.sh
bash scripts/setup_longcat.sh
bash scripts/setup_audio8.sh
```

需要同时保留 Qwen3-TTS：

```bash
TTS_PROVIDER=both bash scripts/setup_tts.sh
```

只安装 Qwen3：

```bash
TTS_PROVIDER=qwen3 bash scripts/setup_tts.sh
```

## 2. TTS 分工

默认策略：

```text
Audio8 0.1B ONNX  -> 批量课程、长期常驻、低内存生产
Qwen3-TTS MLX     -> 精品片头、情绪 / 指令控制、高表达配音
```

Manifest 不写 `tts.provider` 时默认 Audio8。为了兼容旧配置，如果 Manifest 里直接填写了 `mlx-community/Qwen3-TTS-*` 的 `model`，系统仍自动识别为 Qwen3。

## 3. 建人物模板

复制：

```bash
cp profiles/profile.example.json profiles/dan.json
```

Audio8 默认音色：

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

Audio8 声音克隆：

```json
{
  "tts": {
    "provider": "audio8",
    "voice": "dan",
    "ref_audio": "../samples/voice-reference.wav",
    "ref_text": "这里必须填写参考音频准确逐字稿"
  }
}
```

第一次使用时系统会自动注册 `dan` 音色；后续可删除 `ref_audio/ref_text`，只保留 `voice: "dan"` 复用已注册音色。

Qwen3 精品配音：

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

`profiles/*.json`、人物照片、声音和母版默认不会进入 Git。

## 4. Prompt 预设

内置：

- `energy_training_studio`：能源科技培训演播室
- `executive_briefing`：高管汇报 / 正式简报
- `power_market_lab`：电力市场数字专家
- `warm_classroom`：亲和课堂
- `neutral_closeup`：中性稳定近景

Web 页面会自动读取这些预设。课程 Manifest 也可以在课程级或片段级引用。

## 5. 课程 Manifest

参考 `examples/course.example.json`。

核心结构：

```json
{
  "id": "course-demo",
  "title": "课程名称",
  "profile": "dan",
  "tts": {
    "provider": "audio8",
    "voice": "dan"
  },
  "prompt_preset": "energy_training_studio",
  "longcat_max_frames": 125,
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
      "script": "这里是课程正文。"
    }
  ]
}
```

Profile 的 TTS 配置是默认值，Manifest 的 `tts` 会覆盖 Profile，便于同一人物临时切换 Audio8 / Qwen3。

## 6. 自动视频引擎策略

当 `engine=auto`：

```text
hero / intro / section  -> LongCat
body                    -> MuseTalk
```

LongCat 当前仍是短段高质量生成。若自动模式下 TTS 音频超过 `longcat_max_frames / 25fps` 的长度，会自动回退到 MuseTalk，并在 `course-report.json` 中记录原因。

如果片段明确写：

```json
"engine": "longcat"
```

但时长超过 LongCat 上限，则直接报错，不悄悄更换引擎。

## 7. 运行

```bash
bash scripts/run_course.sh examples/course.example.json
```

输出：

```text
outputs/courses/<course-id>/course.mp4
```

中间文件：

```text
workspace/courses/<course-id>/
  audio/
  clips/
  compose/
  course-report.json
```

`course-report.json` 会同时记录课程实际使用的 `tts_provider` 以及每个片段实际使用的数字人引擎。

## 8. 内存策略

针对 M5 Pro 48GB：

- Audio8 是独立 CPU ONNX 服务，保持常驻，避免每段重新加载。
- Qwen3 是 MLX 模型，批量生成配音后会主动释放 MLX cache。
- LongCat / MuseTalk 继续在主视频流程串行执行。

因此 Audio8 更适合作为日常批量课程默认 TTS；Qwen3 不删除，保留为精品声音路径。

## 9. 混剪策略

当前版本优先可靠性：所有生成片段先统一到：

```text
1920 × 1080
25 fps
H.264 / yuv420p
AAC 48 kHz
```

然后使用 FFmpeg concat 拼接。后续再增加：

- 转场
- 自动字幕
- PPT 画面插入
- 章节标题
- 背景音乐 ducking
- 片头片尾模板
