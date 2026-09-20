from __future__ import annotations

import os
import platform
import shutil

from .base import EngineError
from .musetalk import MuseTalkMLXEngine


_BACKEND_ALIASES = {
    "mlx": "mlx",
    "apple": "mlx",
    "apple-silicon": "mlx",
    "mac": "mlx",
    "cuda": "cuda",
    "nvidia": "cuda",
    "pytorch-cuda": "cuda",
}


def normalize_musetalk_backend(value: str | None = None) -> str:
    raw = (value or os.getenv("REMOTE_WORKER_RENDER_BACKEND", "mlx")).strip().lower()
    if raw == "auto":
        if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
            return "mlx"
        if platform.system() == "Linux" and shutil.which("nvidia-smi"):
            return "cuda"
        raise EngineError("cannot auto-detect a supported MuseTalk accelerator")
    backend = _BACKEND_ALIASES.get(raw)
    if backend is None:
        raise EngineError(f"unsupported MuseTalk backend: {raw or 'empty'}")
    return backend


def create_musetalk_engine(backend: str | None = None):
    selected = normalize_musetalk_backend(backend)
    if selected == "mlx":
        return MuseTalkMLXEngine()
    if selected == "cuda":
        from .musetalk_cuda import MuseTalkCUDAEngine

        return MuseTalkCUDAEngine()
    raise EngineError(f"unsupported MuseTalk backend: {selected}")
