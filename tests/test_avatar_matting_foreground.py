from __future__ import annotations

import cv2
import numpy as np

from app.saas.avatar_matting_engine import _SceneForegroundRecovery


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
