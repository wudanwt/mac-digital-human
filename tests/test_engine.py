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


def test_landmark_cache_must_be_complete_and_have_a_face(tmp_path: Path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    coords_file = tmp_path / "coords.pkl"
    payload = {
        "coords": [(10, 20, 110, 150), (11, 21, 111, 151)],
        "fps": 25,
        "frames": ["0.png", "1.png"],
        "n": 2,
    }
    for name in payload["frames"]:
        (frames_dir / name).write_bytes(b"png")
    with coords_file.open("wb") as f:
        pickle.dump(payload, f)

    assert MuseTalkMLXEngine._landmark_cache_complete(coords_file, frames_dir) is True

    (frames_dir / "1.png").unlink()
    assert MuseTalkMLXEngine._landmark_cache_complete(coords_file, frames_dir) is False
