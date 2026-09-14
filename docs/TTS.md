# TTS 双引擎

本项目把 TTS 分成两条路径：

| Provider | 实现 | 推荐用途 |
| --- | --- | --- |
| `audio8` | Audio8 0.1B INT8 ONNX / CPU | 默认生产、批量课程、低内存常驻 |
| `qwen3` | MLX-Audio + Qwen3-TTS | 精品配音、情绪 / 指令控制 |

## Audio8 安装

```bash
bash scripts/setup_audio8.sh
```

安装器会：

1. 固定克隆 `Edge0-AI/Audio8_TTS`。
2. 下载 `Audio8/audio8-TTS-0.1B-ONNX-INT8`。
3. 在官方 `onnx_runtime_0_1b_int8/` 内建立独立 `.venv`。
4. 注册官方 `default` 音色。

启动 / 停止：

```bash
bash scripts/start_audio8.sh
bash scripts/stop_audio8.sh
```

检查：

```bash
.venv/bin/python scripts/check_tts.py --provider audio8
```

Audio8 adapter 默认会自动拉起本地服务，因此课程任务通常不需要手工先启动。

## Audio8 音色克隆

参考音频建议 0.5~30 秒，并提供准确逐字稿。

显式注册：

```bash
.venv/bin/python scripts/register_audio8_voice.py \
  --name dan \
  --audio samples/voice-reference.wav \
  --text "这里填写参考音频准确逐字稿"
```

然后 Profile 只需要：

```json
{
  "tts": {
    "provider": "audio8",
    "voice": "dan"
  }
}
```

也可以直接在 Profile 写 `ref_audio + ref_text`，第一次课程运行时自动注册。

## Qwen3 安装

```bash
bash scripts/setup_qwen3_tts.sh
```

或者两套一起安装：

```bash
TTS_PROVIDER=both bash scripts/setup_tts.sh
```

使用：

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

## Provider 选择规则

1. 明确写 `provider` 时按指定 Provider。
2. 未写 Provider，但 `model` 是 `Qwen3-TTS` 时，为兼容旧 Manifest 自动走 Qwen3。
3. 其他情况默认 Audio8。

## M5 Pro 48GB 资源策略

Audio8 运行在隔离的 CPU ONNX 服务中，可以跨课程保持常驻；LongCat / MuseTalk 仍在主视频流程串行执行。Qwen3 是 MLX 路线，用于精品声音时会在批量配音结束后释放 MLX cache。

因此推荐：

```text
课程正文 / 大批量       -> Audio8
精品开场 / 强情绪配音   -> Qwen3
数字人视频              -> LongCat / MuseTalk
```

## 上游固定版本

当前 Audio8 代码固定到：

```text
Edge0-AI/Audio8_TTS
07e40f5d0b03fc473635ef378654bfb581027ac3
```

模型：

```text
Audio8/audio8-TTS-0.1B-ONNX-INT8
```

本仓库不重新发布模型权重。商业使用前仍需分别核对代码与模型权重许可证。
