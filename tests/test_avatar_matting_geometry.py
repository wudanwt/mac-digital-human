from __future__ import annotations

import numpy as np

from app.saas.avatar_matting_engine import _EnclosedForegroundRecovery


def test_closed_lower_podium_panel_is_recovered() -> None:
    mask = np.zeros((400, 300), dtype=np.uint8)
    mask[140:160, 65:235] = 255  # broad podium top
    mask[160:355, 110:125] = 255  # left rail
    mask[160:355, 175:190] = 255  # right rail
    mask[160:250, 125:175] = 255  # upper panel is already correctly segmented
    mask[350:370, 75:225] = 255  # base closes the pale panel

    recovery = _EnclosedForegroundRecovery(mask)

    assert recovery.enabled
    assert recovery.recovered_ratio > 0.008
    assert recovery.apply(mask)[300, 150] == 255
    assert recovery.apply(mask)[300, 45] == 0


def test_open_background_between_legs_is_not_filled() -> None:
    mask = np.zeros((400, 300), dtype=np.uint8)
    mask[70:200, 110:190] = 255
    mask[200:380, 105:130] = 255
    mask[200:380, 170:195] = 255

    recovery = _EnclosedForegroundRecovery(mask)

    assert not recovery.enabled
    assert recovery.apply(mask)[300, 150] == 0
