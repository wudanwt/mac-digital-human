from __future__ import annotations

import pickle
from pathlib import Path

from app.engine import MuseTalkMLXEngine


def test_repair_missing_coords(tmp_path: Path):
    coords_file = tmp_path / "coords.pkl"
    log_file = tmp_path / "render.log"
    payload = {
        "coords": [
            (0.0, 0.0, 0.0, 0.0),
            (10, 20, 110, 150),
            (0.0, 0.0, 0.0, 0.0),
            (12, 21, 112, 151),
        ],
        "fps": 25,
        "frames": ["0.png", "1.png", "2.png", "3.png"],
    }
    with coords_file.open("wb") as f:
        pickle.dump(payload, f)

    repaired = MuseTalkMLXEngine()._repair_missing_coords(coords_file, log_file)
    assert repaired == 2

    with coords_file.open("rb") as f:
        result = pickle.load(f)
    assert result["coords"][0] == (10, 20, 110, 150)
    assert result["coords"][2] == (10, 20, 110, 150)
