from app.saas.course_studio_ui import JS


def test_script_media_cue_prototype_is_exposed_in_script_review() -> None:
    assert 'id="addMediaCue"' in JS
    assert "＋ 内容镜头" in JS
    assert "media_cues:deep(s.media_cues||[])" in JS
    assert "selectedNarrationAnchor" in JS
    assert "reconcileMediaCues" in JS
    assert "needs_review" in JS
    assert "替换 PPT 区" in JS
    assert "全屏展示" in JS
    assert "画中画" in JS


def test_script_media_cue_prototype_warns_before_render() -> None:
    assert "当前分支只验证交互与草稿保存" in JS
    assert "最终成片暂不应用这些镜头" in JS
