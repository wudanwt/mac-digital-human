# Known Limitations

- Phase 1 changes lip movement; it does not synthesize new full-body gestures.
- The MLX neural core is native Apple Silicon, but face detection/parsing still use CPU/PyTorch/ONNX utilities.
- Web jobs are intentionally serialized because the current upstream helper uses a shared temporary frame folder.
- Web job state is memory-only; restarting the API loses status history, although rendered files remain on disk.
- The first full end-to-end validation still has to be run on the target M5 Pro 48GB machine with real video/audio.
