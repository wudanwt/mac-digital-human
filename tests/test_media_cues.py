from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.composer import ComposeConfig, media_duration
from app.saas.media_cues import (
    apply_media_cues,
    media_cue_asset_ids,
    resolve_media_cue_timeline,
    validate_media_cue_definitions,
)


def _cue(text: str, narration: str, *, cue_id: str = "cue-1", asset_id: str = "asset-1", **extra):
    start = narration.index(text)
    return {
        "id": cue_id,
        "asset_id": asset_id,
        "media_type": extra.pop("media_type", "video"),
        "display_mode": extra.pop("display_mode", "fullscreen"),
        "status": "valid",
        "anchor": {
            "start_offset": start,
            "end_offset": start + len(text),
            "selected_text": text,
            "prefix": narration[max(0, start - 12):start],
            "suffix": narration[start + len(text):start + len(text) + 12],
        },
        "source_start_ms": 0,
        "source_end_ms": None,
        "audio_mode": "mute",
        "audio_gain": 0.2,
        "enter_transition": "cut",
        "exit_transition": "cut",
        "overlay_position": "right_top",
        **extra,
    }


def test_media_cue_timeline_tracks_text_and_reports_asset_ids() -> None:
    narration = "开场介绍。这里展示现场视频。然后回到课程讲解。"
    cue = _cue("这里展示现场视频。", narration)

    timeline = resolve_media_cue_timeline([cue], narration=narration, audio_duration=10.0)

    assert media_cue_asset_ids([cue]) == {"asset-1"}
    assert len(timeline) == 1
    assert 0 < timeline[0].start_seconds < timeline[0].end_seconds < 10.0
    assert timeline[0].alignment_quality == "estimated"

    moved = "新增一句说明。" + narration
    moved_timeline = resolve_media_cue_timeline([cue], narration=moved, audio_duration=12.0)
    assert moved_timeline[0].start_seconds > timeline[0].start_seconds


def test_media_cue_validation_rejects_overlap_and_stale_anchor() -> None:
    narration = "第一段内容。第二段内容。第三段内容。"
    first = _cue("第一段内容。第二段内容。", narration, cue_id="a", asset_id="a1")
    second = _cue("第二段内容。第三段内容。", narration, cue_id="b", asset_id="a2")
    issues = validate_media_cue_definitions([first, second], narration=narration)
    assert any("重叠" in issue for issue in issues)

    stale = _cue("第二段内容。", narration)
    stale["status"] = "needs_review"
    stale["anchor"]["selected_text"] = "已经删除的句子"
    stale_issues = validate_media_cue_definitions([stale], narration=narration)
    assert any("重新确认" in issue for issue in stale_issues)


def _run(command: list[str]) -> None:
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)


def _pixel(path: Path, second: float) -> tuple[int, int, int]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{second:.3f}",
            "-i",
            str(path),
            "-vf",
            "scale=1:1",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert len(proc.stdout) >= 3
    return tuple(proc.stdout[:3])


def test_ffmpeg_media_cue_fullscreen_overlay(tmp_path: Path) -> None:
    base = tmp_path / "base.mp4"
    insert = tmp_path / "insert.mp4"
    output = tmp_path / "output.mp4"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=4:r=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4:sample_rate=48000",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            str(base),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=160x90:d=1:r=25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(insert),
        ]
    )

    narration = "开场说明。现在展示案例现场。最后回到讲解。"
    cue = _cue("现在展示案例现场。", narration)
    rendered, timeline = apply_media_cues(
        base_video=base,
        output_path=output,
        raw_cues=[cue],
        asset_paths={"asset-1": insert},
        narration=narration,
        audio_duration=4.0,
        ppt_box=None,
        config=ComposeConfig(width=320, height=180, fps=25),
    )

    assert rendered == output
    assert output.exists()
    assert media_duration(output) == pytest.approx(4.0, abs=0.12)
    assert len(timeline) == 1

    start = timeline[0]["start_seconds"]
    end = timeline[0]["end_seconds"]
    during = _pixel(output, (start + end) / 2)
    before = _pixel(output, max(0.05, start - 0.25))
    assert during[0] > during[2]  # inserted red frame
    assert before[2] > before[0]  # original blue frame
