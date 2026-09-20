from __future__ import annotations

import os
import platform
import subprocess
from functools import lru_cache


@lru_cache(maxsize=None)
def ffmpeg_encoder_available(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0 and name in (proc.stdout + proc.stderr)


@lru_cache(maxsize=None)
def ffmpeg_encoder_usable(name: str) -> bool:
    if not ffmpeg_encoder_available(name):
        return False
    if name != "h264_nvenc":
        return True
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:r=25:d=0.04",
                "-frames:v",
                "1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def resolve_video_encoder(value: str | None = None) -> str:
    raw = (value or os.getenv("VIDEO_ENCODER_BACKEND", "libx264")).strip().lower()
    aliases = {
        "software": "libx264",
        "x264": "libx264",
        "libx264": "libx264",
        "nvenc": "nvenc",
        "h264_nvenc": "nvenc",
    }
    if raw == "auto":
        if platform.system() == "Linux" and ffmpeg_encoder_usable("h264_nvenc"):
            return "nvenc"
        return "libx264"
    backend = aliases.get(raw)
    if backend is None:
        raise ValueError(f"unsupported VIDEO_ENCODER_BACKEND: {raw or 'empty'}")
    if backend == "nvenc" and not ffmpeg_encoder_usable("h264_nvenc"):
        strict = os.getenv("VIDEO_ENCODER_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}
        if strict:
            raise RuntimeError("VIDEO_ENCODER_BACKEND=nvenc but ffmpeg has no h264_nvenc encoder")
        return "libx264"
    return backend


def ffmpeg_video_encode_args(
    *,
    crf: int = 18,
    software_preset: str = "medium",
    backend: str | None = None,
) -> list[str]:
    selected = resolve_video_encoder(backend)
    if selected == "nvenc":
        preset = os.getenv("VIDEO_ENCODER_NVENC_PRESET", "p4").strip() or "p4"
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            preset,
            "-cq",
            str(int(crf)),
            "-b:v",
            "0",
        ]
    return [
        "-c:v",
        "libx264",
        "-preset",
        software_preset,
        "-crf",
        str(int(crf)),
    ]


def video_encoder_info(value: str | None = None) -> dict[str, object]:
    requested = value or os.getenv("VIDEO_ENCODER_BACKEND", "libx264")
    selected = resolve_video_encoder(value)
    return {
        "requested": requested,
        "selected": selected,
        "ffmpeg_h264_nvenc": ffmpeg_encoder_available("h264_nvenc"),
        "ffmpeg_h264_nvenc_usable": ffmpeg_encoder_usable("h264_nvenc"),
    }
