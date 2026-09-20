from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest
from PIL import Image
from PIL import ImageFont

from app.composer import ComposeConfig, CourseComposer, media_duration


def test_prevalidated_concat_skips_per_page_transcodes(monkeypatch, tmp_path: Path) -> None:
    composer = CourseComposer()
    clips = [tmp_path / "one.mp4", tmp_path / "two.mp4"]
    output = tmp_path / "course.mp4"
    commands: list[list[str]] = []
    monkeypatch.setattr(composer, "normalize", lambda *_: (_ for _ in ()).throw(AssertionError("unexpected transcode")))
    monkeypatch.setattr(composer, "_run", lambda command: commands.append(command))

    assert composer.concat(clips, output, tmp_path / "concat", prevalidated=True) == output
    assert len(commands) == 1
    assert commands[0][commands[0].index("-c") + 1] == "copy"
    manifest = (tmp_path / "concat" / "concat.txt").read_text(encoding="utf-8")
    assert all(str(clip) in manifest for clip in clips)
    assert not (tmp_path / "concat" / "normalized").exists()


def test_subtitles_and_ai_badge_share_one_encoding_pass(monkeypatch, tmp_path: Path) -> None:
    composer = CourseComposer()
    source = tmp_path / "course.mp4"
    srt = tmp_path / "course.srt"
    badge = tmp_path / "badge.png"
    output = tmp_path / "result.mp4"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest caption\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(composer, "load_subtitle_font", lambda *_: ImageFont.load_default())
    monkeypatch.setattr(composer, "_run", lambda command: commands.append(command))
    monkeypatch.setattr("app.composer.media_duration", lambda *_: 1.0)

    assert composer.burn_in_subtitles(source, srt, output, ai_badge_path=badge) == output
    assert len(commands) == 1
    command = commands[0]
    assert str(badge) in command
    assert "overlay=W-w-24:H-h-24:format=auto" in command[command.index("-filter_complex") + 1]
    assert "comment=AI-generated digital human content" in command
    assert command[command.index("-t") + 1] == "1.000"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is required")
def test_fast_finalize_produces_playable_labeled_video(monkeypatch, tmp_path: Path) -> None:
    composer = CourseComposer(ComposeConfig(width=320, height=180, fps=5))
    monkeypatch.setattr(composer, "load_subtitle_font", lambda *_: ImageFont.load_default())
    clips = [tmp_path / "one.mp4", tmp_path / "two.mp4"]
    for color, clip in zip(("blue", "green"), clips):
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=5:d=1",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-ac", "1", "-shortest", str(clip),
            ],
            check=True,
        )
    raw = composer.concat(clips, tmp_path / "course.mp4", tmp_path / "concat", prevalidated=True)
    srt = tmp_path / "course.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest caption\n", encoding="utf-8")
    badge = tmp_path / "badge.png"
    Image.new("RGBA", (50, 20), (255, 255, 255, 200)).save(badge)
    labeled = composer.burn_in_subtitles(raw, srt, tmp_path / "labeled.mp4", ai_badge_path=badge)
    assert labeled.exists()
    assert media_duration(labeled) == pytest.approx(2.0, abs=0.25)
