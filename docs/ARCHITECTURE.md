# Architecture

## Phase 1 data flow

```text
video -> ffmpeg 25fps -> DWPose + S3FD -> bbox metadata
                                      |
audio -> ffmpeg 16k mono -> Whisper-MLX -> audio embeddings
                                      |
face crop -> VAE-MLX -> MuseTalk UNet-MLX -> VAE-MLX -> face blend -> ffmpeg -> MP4
```

## Runtime split

- MLX / Metal: MuseTalk VAE, UNet, Whisper encoder.
- CPU / PyTorch: S3FD detector and BiSeNet face parsing.
- ONNX Runtime: DWPose.
- FFmpeg: normalization and muxing.

## Why jobs are serialized

The current upstream `build_video.py` uses a shared frame staging directory inside the cloned MuseTalk-MLX repository. The Web/API job manager therefore uses a process-level lock so two renders cannot overwrite the same temporary frames.

A later version should replace the upstream helper with our own workspace-scoped renderer, at which point parallel jobs can be enabled.
