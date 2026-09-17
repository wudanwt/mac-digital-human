from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from app.saas.avatar_matting_engine import PortraitMattingEngine, _SceneForegroundRecovery, despill_green, is_green_screen


def test_recovery_fills_translucent_desk_edge_without_restoring_background() -> None:
    rgb = np.full((160, 200, 3), 245, dtype=np.uint8)
    rgb[40:125, 70:130] = (60, 55, 70)
    rgb[118:160, 20:180] = (75, 45, 35)

    portrait = np.zeros((160, 200), dtype=np.uint8)
    portrait[40:125, 70:130] = 255
    portrait[118:160, 20:180] = 255
    portrait[118:121, 30:170] = 80

    recovery = _SceneForegroundRecovery(rgb, portrait)
    result = recovery.apply(rgb, portrait)

    assert recovery.enabled
    assert result[119, 40] > 220
    assert result[10, 40] == 0
    assert result[119, 10] == 0


def test_green_screen_detection_requires_dominant_border() -> None:
    green = np.full((96, 96, 3), (20, 240, 15), dtype=np.uint8)
    green[20:76, 20:76] = (210, 90, 80)
    assert is_green_screen(green)

    blue = np.full_like(green, (30, 80, 210))
    assert not is_green_screen(blue)
    white = np.full_like(green, (245, 245, 245))
    white[20:76, 20:76] = (20, 240, 15)
    assert not is_green_screen(white)


def test_despill_only_changes_green_near_alpha_edge() -> None:
    rgb = np.full((32, 32, 3), (20, 240, 15), dtype=np.uint8)
    rgb[8:24, 8:24] = (170, 205, 150)
    alpha = np.zeros((32, 32), dtype=np.uint8)
    alpha[8:24, 8:24] = 255
    alpha[8, 8:24] = 180

    result = despill_green(rgb, alpha)
    assert result[8, 12, 1] <= max(result[8, 12, 0], result[8, 12, 2]) + 4
    assert result[9, 12, 1] <= max(result[9, 12, 0], result[9, 12, 2]) + 4
    assert np.array_equal(result[16, 16], rgb[16, 16])
    assert np.array_equal(result[:, :, [0, 2]], rgb[:, :, [0, 2]])

    rgb[16, 16] = (25, 85, 15)
    assert despill_green(rgb, alpha)[16, 16, 1] <= 29


def test_green_screen_matting_previews_despill_without_model_load(tmp_path, monkeypatch) -> None:
    source = tmp_path / "green.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 25, (96, 96))
    assert writer.isOpened()
    frame = np.full((96, 96, 3), (15, 240, 20), dtype=np.uint8)
    frame[20:76, 20:76] = (150, 120, 190)
    frame[20, 20:76] = (110, 220, 140)
    for _ in range(4):
        writer.write(frame)
    writer.release()

    mask = np.zeros((96, 96), dtype=np.uint8)
    mask[20:76, 20:76] = 255
    mask[20, 20:76] = 150
    monkeypatch.setenv("AVATAR_MATTING_PRESERVE_FOREGROUND", "0")
    monkeypatch.setenv("AVATAR_MATTING_EDGE_BLUR", "0")
    monkeypatch.setenv("AVATAR_MATTING_TEMPORAL_SMOOTHING", "0")
    engine = PortraitMattingEngine()
    monkeypatch.setattr(engine, "_new_session", lambda: type("Session", (), {
        "name": "stub", "predict": lambda self, rgb: mask,
    })())

    result = engine.process(source, tmp_path / "result")
    poster = np.asarray(Image.open(result.poster_png).convert("RGBA"))
    assert result.green_screen
    assert poster[20, 48, 3] == 150
    assert poster[20, 48, 1] <= max(poster[20, 48, 0], poster[20, 48, 2]) + 4

    cap = cv2.VideoCapture(str(result.white_preview))
    ok, preview = cap.read()
    cap.release()
    assert ok
    edge_bgr = preview[20, 48]
    assert int(edge_bgr[1]) <= max(int(edge_bgr[0]), int(edge_bgr[2])) + 12
