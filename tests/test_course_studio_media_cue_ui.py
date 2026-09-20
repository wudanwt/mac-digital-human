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
    assert "previewMediaCues" in JS
    assert "openMediaCuePreview" in JS
    assert "QUICK CONTENT-SHOT PREVIEW" in JS
    assert "layoutPreviewMedia" in JS
    assert "updateMediaCuePreviewButton" in JS
    assert "runMediaCuePreview" in JS
    assert "正在准备预览" in JS


def test_script_media_cue_ui_describes_automatic_render_timeline() -> None:
    assert "实际页面音频时长自动计算切入与退出时间" in JS
    assert "将按讲稿位置自动切换并合成到最终成片" in JS
    assert "最终成片暂不应用这些镜头" not in JS
    assert "使用本页 TTS 试听真实时长驱动" in JS
    assert "当前按讲稿估算时间" in JS
