from __future__ import annotations

import inspect

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
