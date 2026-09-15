# Digital Human TTS Core

这是从 Workout-TTS 提取出的独立 CosyVoice 2 语音核心，包含文本清洗、长文本分句、零样本音色克隆和 WAV 输出。

## 目录

- `tts_core/`：可直接复制到数字人项目的 Python 包
- `models/CosyVoice2-0.5B/`：CosyVoice 2 模型权重
- `vendor/CosyVoice/`：模型推理源码
- `voices/wudan/`：示例参考音频与逐字匹配的参考文本
- `api.py`：独立 HTTP 服务
- `example.py`：Python 进程内调用示例

## Python 接入

```python
from tts_core import CosyVoiceService

tts = CosyVoiceService("/path/to/digital-human-tts")
result = tts.synthesize(
    text="你好，我是数字人讲解员。",
    reference_audio="/path/to/reference.wav",
    reference_text="参考音频中实际说出的完整文字。",
    speed=1.0,
)
# result.audio: float32 单声道 numpy 数组
# result.sample_rate: 24000
```

## HTTP 接入

```bash
TTS_BUNDLE_DIR=/path/to/digital-human-tts \
python -m uvicorn api:app --host 127.0.0.1 --port 8801
```

`POST /synthesize` 接收 JSON，返回 `audio/wav`：

```json
{
  "text": "你好，我是数字人讲解员。",
  "reference_audio": "/path/to/reference.wav",
  "reference_text": "参考音频中实际说出的完整文字。",
  "speed": 1.0
}
```

模型常驻内存，调用方不要为每句话重新创建 `CosyVoiceService`。参考文本必须与参考录音逐字一致，否则模型可能把参考词带进合成内容。
