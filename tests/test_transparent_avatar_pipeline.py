from __future__ import annotations

import inspect
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw

from app.composer import ComposeConfig, media_duration
from app.saas.avatar_alpha import AlphaCycleCache
from app.saas.avatar_matting_ui import JS as avatar_matting_js
from app.saas.course_avatar_mode_ui import JS as course_avatar_mode_js
from app.saas.transparent_composer import TransparentCourseComposer
from app.saas.worker_entry import BackgroundAwareMLXCourseHandler


def test_alpha_cycle_matches_musetalk_ping_pong_sequence() -> None:
    assert [AlphaCycleCache.cycle_index(4, i) for i in range(12)] == [0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3]


def test_asset_ui_exposes_one_time_matting_and_both_previews() -> None:
    assert "/avatar-matting/" in avatar_matting_js
    assert "生成透明资产" in avatar_matting_js
    assert "透明预览" in avatar_matting_js
    assert "白底预览" in avatar_matting_js
    assert "课程生成直接复用 Alpha" in avatar_matting_js


def test_course_ui_persists_per_slide_avatar_mode() -> None:
    assert "avatar_mode" in course_avatar_mode_js
    assert "transparent" in course_avatar_mode_js
    assert "white" in course_avatar_mode_js
    assert "original" in course_avatar_mode_js
    assert "将当前模式应用到全部页面" in course_avatar_mode_js
    assert "studio-avatar-matte-overlay" in course_avatar_mode_js


def test_final_composer_only_consumes_precomputed_alpha() -> None:
    source = inspect.getsource(TransparentCourseComposer)
    assert "avatar_alpha_video" in source
    assert "alphamerge" in source
    assert "rembg" not in source
    assert "new_session" not in source


def test_worker_requires_ready_alpha_for_transparent_or_white_modes() -> None:
    source = inspect.getsource(BackgroundAwareMLXCourseHandler._prepare_matte_context)
    assert "transparent" in source
    assert "white" in source
    assert "ready_matting_assets" in source
    assert "透明资产尚未处理完成" in source


def test_transparent_composer_executes_real_ffmpeg_overlay(tmp_path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not available")

    slide = tmp_path / "slide.png"
    Image.new("RGB", (640, 360), "#20334a").save(slide)

    mask_png = tmp_path / "mask.png"
    mask = Image.new("L", (160, 300), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 0, 79, 299), fill=255)
    mask.save(mask_png)

    avatar = tmp_path / "avatar.mp4"
    alpha = tmp_path / "alpha.mp4"
    audio = tmp_path / "audio.wav"
    output = tmp_path / "result.mp4"

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=160x300:r=25:d=0.6",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(avatar),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", "25", "-i", str(mask_png), "-t", "0.6",
            "-an", "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", str(alpha),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "0.6",
            "-c:a", "pcm_s16le", str(audio),
        ],
        check=True,
    )

    composer = TransparentCourseComposer(ComposeConfig(width=640, height=360, fps=25, crf=22, audio_rate=48000))
    composer.compose_segment_layout(
        avatar_video=avatar,
        avatar_alpha_video=alpha,
        avatar_mode="transparent",
        audio=audio,
        slide_image=slide,
        layout="pip",
        target=output,
        pip_box={"x": 0.70, "y": 0.10, "w": 0.26, "h": 0.82},
        ppt_box={"x": 0.04, "y": 0.10, "w": 0.62, "h": 0.76},
    )

    assert output.exists()
    assert output.stat().st_size > 0
    assert media_duration(output) >= 0.5
