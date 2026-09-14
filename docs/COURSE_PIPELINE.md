# 课程批量生产流水线

目标：把“脚本 → TTS → 数字人片段 → 自动混剪”变成一次命令，而不是逐段手工操作。

## 1. 安装完整生产组件

```bash
WITH_LONGCAT=1 WITH_TTS=1 bash scripts/setup.sh
```

也可以分开安装：

```bash
bash scripts/setup.sh
bash scripts/setup_longcat.sh
bash scripts/setup_tts.sh
```

TTS 使用 Apple Silicon 原生的 MLX-Audio。默认模型为：

```text
mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit
```

需要声音克隆时使用：

```text
mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16
```

并在人物模板中配置 `ref_audio + ref_text`。

## 2. 建人物模板

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
    "ref_text": "这里必须填写参考音频准确逐字稿"
  }
}
```

`profiles/*.json`、人物照片、声音和母版默认不会进入 Git。

## 3. Prompt 预设

内置：

- `energy_training_studio`：能源科技培训演播室
- `executive_briefing`：高管汇报 / 正式简报
- `power_market_lab`：电力市场数字专家
- `warm_classroom`：亲和课堂
- `neutral_closeup`：中性稳定近景

Web 页面会自动读取这些预设。课程 Manifest 也可以在课程级或片段级引用。

## 4. 课程 Manifest

参考 `examples/course.example.json`。

核心结构：

```json
{
  "id": "course-demo",
  "title": "课程名称",
  "profile": "dan",
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

## 5. 自动引擎策略

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

## 6. 运行

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

## 7. 内存策略

针对 M5 Pro 48GB，流水线不是把所有模型同时驻留：

1. 先加载 TTS，批量生成全部配音。
2. 主动释放 TTS / MLX cache。
3. 再按片段顺序运行 LongCat / MuseTalk。
4. 最后 FFmpeg 统一规格并拼接。

这样比 TTS + LongCat 同时驻留更适合 48GB 统一内存。

## 8. 混剪策略

当前版本优先可靠性：所有生成片段先统一到：

```text
1920 × 1080
25 fps
H.264 / yuv420p
AAC 48 kHz
```

然后使用 FFmpeg concat 进行无损二次拼接。后续再增加：

- 转场
- 自动字幕
- PPT 画面插入
- 章节标题
- 背景音乐 ducking
- 片头片尾模板

当前不先堆这些视觉功能，优先验证整条课程生产链稳定性。
