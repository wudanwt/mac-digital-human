# M5 Pro 48GB 首机验收

在目标 Mac 上按顺序执行：

```bash
bash scripts/setup.sh
.venv/bin/python scripts/check_runtime.py --variant q8
```

然后准备：

```text
samples/master.mp4
samples/voice.wav
```

运行：

```bash
bash scripts/run_avatar.sh --video samples/master.mp4 --audio samples/voice.wav --variant q8
```

验收项：

- 环境检查全部 ready。
- 人脸关键点阶段无持续丢脸。
- 输出 MP4 音视频长度正确。
- 嘴型与中文语音基本同步。
- 嘴周没有大面积闪烁/错位。
- `workspace/<job>/render.log` 可用于定位错误。

如果 Q8 稳定，再下载 FP16：

```bash
.venv/bin/python scripts/setup_models.py --variant fp16
```

并用同一素材 A/B 对比画质与速度。
