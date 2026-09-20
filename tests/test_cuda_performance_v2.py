from __future__ import annotations

from pathlib import Path

import app.video_encoding as video_encoding
from app.engines.musetalk_cuda import MuseTalkCUDAEngine


def test_video_encoder_default_preserves_existing_software_path(monkeypatch):
    monkeypatch.delenv("VIDEO_ENCODER_BACKEND", raising=False)
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_available", lambda _name: True)
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_usable", lambda _name: True)
    assert video_encoding.resolve_video_encoder() == "libx264"
    args = video_encoding.ffmpeg_video_encode_args(crf=18, software_preset="medium")
    assert args[:2] == ["-c:v", "libx264"]
    assert "h264_nvenc" not in args


def test_video_encoder_auto_uses_nvenc_on_linux(monkeypatch):
    monkeypatch.setenv("VIDEO_ENCODER_BACKEND", "auto")
    monkeypatch.setattr(video_encoding.platform, "system", lambda: "Linux")
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_available", lambda name: name == "h264_nvenc")
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_usable", lambda name: name == "h264_nvenc")
    assert video_encoding.resolve_video_encoder() == "nvenc"
    args = video_encoding.ffmpeg_video_encode_args(crf=18, software_preset="medium")
    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert "-cq" in args


def test_video_encoder_nvenc_falls_back_without_encoder(monkeypatch):
    monkeypatch.setenv("VIDEO_ENCODER_BACKEND", "nvenc")
    monkeypatch.delenv("VIDEO_ENCODER_STRICT", raising=False)
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_available", lambda _name: False)
    monkeypatch.setattr(video_encoding, "ffmpeg_encoder_usable", lambda _name: False)
    assert video_encoding.resolve_video_encoder() == "libx264"


def test_cuda_streaming_is_isolated_and_has_upstream_fallback(monkeypatch):
    monkeypatch.delenv("MUSETALK_CUDA_STREAMING", raising=False)
    monkeypatch.delenv("MUSETALK_CUDA_VIDEO_ENCODER", raising=False)
    engine = MuseTalkCUDAEngine()
    assert engine.streaming is True
    assert engine.video_encoder == "auto"

    source = Path("scripts/cloud/musetalk_cuda_stream.py").read_text(encoding="utf-8")
    assert "rawvideo" in source
    assert "pipe:0" in source
    assert "cv2.imwrite" not in source
    assert "h264_nvenc" in source
