# Avatar Profiles

这里保存**本机人物模板**，用于避免每次生成都重新上传照片、重复填写 Prompt / TTS 配置。

实际 `*.json`、人物照片和声音参考默认不提交 Git。仓库只保留 `profile.example.json` 作为格式示例。

复制示例：

```bash
cp profiles/profile.example.json profiles/dan.json
```

## Audio8：推荐的生产型声音配置

默认课程 TTS 是 **Audio8 0.1B INT8 ONNX**。如果先使用官方默认音色：

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

要注册并复用自己的 Audio8 克隆音色，把 `voice` 改成一个稳定名称，并提供参考录音与准确逐字稿：

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

第一次课程生成会自动调用 Audio8 的本地音色注册接口；后续课程只需要 `voice: "dan"` 即可复用。参考录音和逐字稿仍只保存在本机 Profile / samples 目录。

## Qwen3：精品 / 高表达备选

需要 Qwen3-TTS 的情绪与指令控制时显式指定：

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

Qwen3 也继续支持 `ref_audio + ref_text` 的零样本声音克隆。
