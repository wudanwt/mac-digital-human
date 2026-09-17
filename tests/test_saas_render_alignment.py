from __future__ import annotations

from app.saas.worker_entry import _align_avatar_filter_graph


def test_avatar_filter_is_bottom_aligned_like_studio_preview() -> None:
    graph = (
        "[1:v]scale=480:756:force_original_aspect_ratio=decrease,"
        "pad=480:756:(ow-iw)/2:(oh-ih)/2:color=black@0,fps=25[avatar];"
        "[slide][avatar]overlay=x=1363:y=270[outv]"
    )
    patched = _align_avatar_filter_graph(graph)
    assert "pad=480:756:(ow-iw)/2:oh-ih:color=black@0" in patched
    assert "(oh-ih)/2:color=black@0" not in patched


def test_non_avatar_filter_keeps_vertical_centering() -> None:
    graph = (
        "[0:v]scale=1248:820:force_original_aspect_ratio=decrease,"
        "pad=1248:820:(ow-iw)/2:(oh-ih)/2:color=black@0,fps=25[ppt_win]"
    )
    assert _align_avatar_filter_graph(graph) == graph
