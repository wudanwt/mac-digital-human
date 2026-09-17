from __future__ import annotations

import inspect

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
