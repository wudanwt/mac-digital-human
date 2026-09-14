# LongCat Avatar 1.5 MLX

本项目的高质量数字人模式基于 `xocialize/longcat-avatar-mlx`，它是美团 `LongCat-Video-Avatar-1.5` 的 Apple MLX 移植。

## 为什么加入 LongCat

MuseTalk 更像“已有视频的高质量口型替换”；LongCat 则会根据参考照片、音频和文本 Prompt 重新生成整个视频片段，因此可以产生更多：

- 表情变化
- 头部运动
- 上半身动态
- 自然动作感
- 场景 / 风格条件

两者不是替代关系：MuseTalk 负责批量和稳定，LongCat 负责精品片段。

## M5 Pro 48GB 推荐配置

```text
variant: q4-merged
resolution: 832 x 480
frames: 93
fps: 25（本项目封装输出）
seed: 42
```

安装：

```bash
bash scripts/setup_longcat.sh
```

默认模型：

```text
mlx-community/LongCat-Video-Avatar-1.5-q4-dmd-merged
```

模型会下载到：

```text
models/longcat/LongCat-Video-Avatar-1.5-q4-dmd-merged/
```

## 运行

```bash
bash scripts/run_avatar.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged \
  --prompt "A professional Chinese male instructor speaking naturally to camera, subtle head movement, natural hand gestures, calm confident expression."
```

输出：

```text
outputs/<job-id>/result.mp4
```

## Prompt 建议

建议至少包含四类信息：

```text
人物身份 + 正在做什么 + 动作节奏 + 场景/光线
```

例如：

```text
A professional Chinese male energy-industry instructor is speaking naturally to camera,
subtle head movement and restrained hand gestures, calm confident expression,
standing in a modern clean training studio, realistic soft lighting,
professional documentary-style framing.
```

不要在第一轮加入过多复杂动作。先确保人物身份和嘴型稳定，再逐步增加镜头和动作描述。

## 参考图片建议

- 单人清晰照片
- 正脸或轻微侧脸
- 头肩 / 半身优先
- 面部无遮挡
- 光线均匀
- 避免极端姿态
- 避免多人同框

## 当前适配方式

本项目没有复制 LongCat MLX 的模型实现，而是：

```text
app/engines/longcat.py
        │
        ▼
scripts/longcat_infer.py
        │
        ▼
vendor/longcat-avatar-mlx
        │
        ▼
models/longcat/<variant>
```

`scripts/longcat_infer.py` 动态加载固定版本的上游 `run_inference.py`，复用它的：

- pipeline 构建
- 图像预处理
- Whisper 特征处理
- umT5 tokenizer / text encoding

然后替换成用户自己的图片、音频和 Prompt，并在生成结束后用 FFmpeg 把音频封装回最终 MP4。

这种方式可以让上游模型实现与本项目的业务编排保持解耦。

## 当前限制

LongCat MLX 上游当前的 v1 重点是单段 AI2V：

- 当前项目未接入 multi-chunk continuation。
- 不适合实时对话。
- 长音频会被最终成片时长截断；建议先用 2–5 秒片段做验证。
- Q8 和 BF16 会显著增加内存压力；M5 Pro 48GB 首先用 Q4。
- 首次加载大模型会明显慢于后续普通 Web 操作。

## 首机验收顺序

建议不要第一条就使用正式课程素材。先用：

1. 一张清晰半身照。
2. 2–3 秒中文语音。
3. `768×432 / 61 frames / q4-merged`。
4. 确认能够完整生成并带音频输出。
5. 再切换 `832×480 / 93 frames`。

如果失败，查看：

```text
workspace/<job-id>/render.log
```

以及：

```bash
.venv/bin/python scripts/check_runtime.py \
  --engine longcat \
  --longcat-variant q4-merged
```
