# Samples

把本地测试素材放到这个目录即可，大文件和人物素材默认被 `.gitignore` 忽略。

建议文件名：

```text
samples/master.mp4   # MuseTalk 母版视频
samples/ref.png      # LongCat 参考人物照片
samples/voice.wav    # 驱动音频
```

MuseTalk：

```bash
bash scripts/run_avatar.sh \
  --engine musetalk \
  --video samples/master.mp4 \
  --audio samples/voice.wav
```

LongCat：

```bash
bash scripts/run_avatar.sh \
  --engine longcat \
  --image samples/ref.png \
  --audio samples/voice.wav \
  --variant q4-merged
```

不要把含有人脸、声音或公司内部信息的测试素材提交到公共仓库。
