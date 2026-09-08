# Troubleshooting

## `engine is not ready`

Run:

```bash
.venv/bin/python scripts/check_runtime.py --variant q8
```

The JSON output shows exactly which model or tool is missing.

## Hugging Face download is slow

Re-run the same setup command; `snapshot_download` resumes cached files. You can also set `HF_HOME` to a disk with more free space.

## Face parsing Google Drive checkpoint cannot download

The current upstream MuseTalk face parser still depends on `79999_iter.pth`. If `gdown` fails, manually obtain the checkpoint referenced by the official MuseTalk project and place it at:

```text
vendor/MuseTalk/models/face-parse-bisent/79999_iter.pth
```

Then re-run `scripts/check_runtime.py`.

## `no face was detected`

Use a more frontal master clip with brighter, stable lighting and a larger visible face. See `docs/RECORDING_GUIDE.md`.

## One or two frames lose the face

The orchestration layer automatically fills intermittent missing boxes with a neighboring valid box. Long stretches of missed detection still indicate unsuitable source video.

## Web UI should only be local

Default:

```bash
bash scripts/run_web.sh
```

LAN access only when intentionally needed:

```bash
HOST=0.0.0.0 bash scripts/run_web.sh
```
