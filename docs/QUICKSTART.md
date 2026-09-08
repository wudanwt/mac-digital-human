# Quickstart

```bash
git clone https://github.com/wudanwt/mac-digital-human.git
cd mac-digital-human
bash scripts/setup.sh
bash scripts/run_web.sh
```

Open `http://127.0.0.1:8000`.

Or render directly:

```bash
bash scripts/run_avatar.sh \
  --video samples/master.mp4 \
  --audio samples/voice.wav \
  --variant q8
```
