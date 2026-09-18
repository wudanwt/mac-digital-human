from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.saas import tts_pipeline
from app.saas.worker import _apply_ai_label


class _DummyTTS:
    def readiness(self):
        return {"ready": True}

    def release(self):
        return None


def test_course_tts_professional_matches_local_zero_shot(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_infer(payload):
        captured["infer"] = dict(payload)
        return "cosyvoice2"

    def fake_create(payload, *, base):
        captured["create"] = dict(payload)
        captured["base"] = base
        return _DummyTTS()

    monkeypatch.setattr(tts_pipeline, "infer_provider", fake_infer)
    monkeypatch.setattr(tts_pipeline, "create_tts", fake_create)
    voice = SimpleNamespace(
        provider="cosyvoice",
        transcript="参考逐字稿",
        settings_json=json.dumps({"instruct": "不应保留", "pause_seconds": 0.31}),
    )
    runtime = tts_pipeline.build_course_tts(
        voice,
        ref_audio=tmp_path / "ref.wav",
        course_settings={
            "speed": 1.1,
            "emotion": "professional",
            "tts": {"pronunciation_replacements": {"优优": "悠悠"}},
        },
        base=tmp_path,
    )
    assert runtime.provider_name == "cosyvoice2"
    assert runtime.speed == 1.1
    assert captured["create"]["ref_text"] == "参考逐字稿"
    assert captured["create"]["ref_audio"].endswith("ref.wav")
    assert "instruct" not in captured["create"]
    assert captured["create"]["pause_seconds"] == 0.31
    assert captured["create"]["pronunciation_replacements"] == {"优优": "悠悠"}


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg required")
def test_ai_label_does_not_require_drawtext_and_preserves_soft_subtitle(tmp_path: Path) -> None:
    base = tmp_path / "base.mp4"
    srt = tmp_path / "caption.srt"
    source = tmp_path / "source.mp4"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,800\n测试字幕\n", encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1:r=25",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(base),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(base), "-i", str(srt), "-c:v", "copy", "-c:a", "copy",
            "-c:s", "mov_text", "-metadata:s:s:0", "language=chi", str(source),
        ],
        check=True,
    )
    labeled = _apply_ai_label(source)
    assert labeled.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(labeled)],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = probe.stdout.splitlines()
    assert "video" in streams
    assert "audio" in streams
    assert "subtitle" in streams
