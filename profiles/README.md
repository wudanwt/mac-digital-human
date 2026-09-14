# Avatar Profiles

这里保存**本机人物模板**，用于避免每次生成都重新上传照片、重复填写 Prompt / TTS 配置。

实际 `*.json`、人物照片和声音参考默认不提交 Git。仓库只保留 `profile.example.json` 作为格式示例。

复制示例：

```bash
cp profiles/profile.example.json profiles/dan.json
```

然后修改成你的本地素材路径：

```json
{
  "id": "dan",
  "name": "丹哥｜能源培训讲师",
  "image": "../samples/ref.png",
  "prompt_preset": "energy_training_studio",
  "tts": {
    "voice": "Dylan",
    "ref_audio": "../samples/voice-reference.wav",
    "ref_text": "这里填写参考音频逐字稿"
  }
}
```

如果设置 `ref_audio + ref_text`，课程流水线可切到 Qwen3-TTS Base 声音克隆；不设置时使用 CustomVoice 预设音色。
