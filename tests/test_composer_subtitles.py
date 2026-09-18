from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from app.composer import ComposeError, CourseComposer


def test_subtitle_font_candidates_include_linux_cjk() -> None:
    candidates = CourseComposer.subtitle_font_candidates()
    assert any("NotoSansCJK" in path for path, _ in candidates)
    assert any(path.startswith("/usr/share/fonts/") for path, _ in candidates)
    assert any("NotoSansCJK" in path and index == 2 for path, index in candidates)


def test_load_subtitle_font_renders_cjk_wider_than_default_bitmap() -> None:
    font = CourseComposer.load_subtitle_font(34)
    sample = "大家好。"
    cjk_width = font.getbbox(sample)[2] - font.getbbox(sample)[0]
    default_width = ImageFont.load_default().getbbox(sample)[2] - ImageFont.load_default().getbbox(sample)[0]
    assert cjk_width >= 34
    assert cjk_width > default_width * 2


def test_subtitle_overlay_card_keeps_readable_cjk(tmp_path) -> None:
    font = CourseComposer.load_subtitle_font(34)
    text = "这节课呢，我们就讲一件事。"
    image = Image.new("RGBA", (1920, 180), (15, 23, 42, 210))
    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((40, 40), text, font=font)
    draw.text((40, 40), text, font=font, fill=(255, 255, 255, 255))
    path = tmp_path / "subtitle-card.png"
    image.save(path)
    assert (bbox[2] - bbox[0]) >= 300
    assert path.exists()


def test_missing_cjk_font_fails_instead_of_tofu(monkeypatch) -> None:
    monkeypatch.setattr(CourseComposer, "subtitle_font_candidates", staticmethod(lambda: (("/tmp/missing-cjk.ttf", 0),)))
    try:
        CourseComposer.load_subtitle_font(34)
    except ComposeError as exc:
        assert "CJK" in str(exc)
    else:
        raise AssertionError("expected ComposeError when no CJK font exists")
