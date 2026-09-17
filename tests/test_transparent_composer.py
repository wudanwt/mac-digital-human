from __future__ import annotations

import inspect

import cv2
import numpy as np

from app.saas.transparent_composer import TransparentCourseComposer


def test_transparent_composer_uses_precomputed_alpha_only() -> None:
    source = inspect.getsource(TransparentCourseComposer.compose_segment_layout)
    assert "alphamerge" in source
    assert "avatar_alpha_video" in source
    assert "rembg" not in source
    assert "oh-ih:color=0x00000000" in source
    assert "mode == \"white\"" in source


def test_transparent_composer_keeps_three_modes_distinct() -> None:
    source = inspect.getsource(TransparentCourseComposer.compose_segment_layout)
    assert '{"transparent", "white"}' in source
    assert "return super().compose_segment_layout" in source


def test_composer_detects_green_master_without_recoloring_other_scenes(tmp_path) -> None:
    for name, color, expected in (
        ("green", (15, 240, 20), True),
        ("blue", (210, 80, 30), False),
    ):
        path = tmp_path / f"{name}.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (96, 96))
        assert writer.isOpened()
        writer.write(np.full((96, 96, 3), color, dtype=np.uint8))
        writer.release()
        assert TransparentCourseComposer._needs_green_despill(path) is expected
