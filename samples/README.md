# Samples

把本地测试素材放到这个目录即可，大文件默认被 `.gitignore` 忽略。

建议文件名：

```text
samples/master.mp4
samples/voice.wav
```

然后运行：

```bash
bash scripts/run_avatar.sh --video samples/master.mp4 --audio samples/voice.wav
```

不要把含有人脸、声音或公司内部信息的测试素材提交到公共仓库。
