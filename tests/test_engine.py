from __future__ import annotations

import pickle
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.engine import MuseTalkMLXEngine
from app.engines.musetalk_runtime import ResidentMuseTalkRuntime


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
        "frames": [str(frames_dir / "0.png"), str(frames_dir / "1.png")],
        "n": 2,
    }
    for name in payload["frames"]:
        Path(name).write_bytes(b"png")
    with coords_file.open("wb") as f:
        pickle.dump(payload, f)

    assert MuseTalkMLXEngine._landmark_cache_complete(coords_file, frames_dir) is True

    (frames_dir / "1.png").unlink()
    assert MuseTalkMLXEngine._landmark_cache_complete(coords_file, frames_dir) is False


def test_repair_without_missing_boxes_preserves_coords_mtime(tmp_path: Path):
    coords_file = tmp_path / "coords.pkl"
    with coords_file.open("wb") as fh:
        pickle.dump({"coords": [(1, 2, 3, 4)]}, fh)
    before = coords_file.stat().st_mtime_ns
    assert MuseTalkMLXEngine()._repair_missing_coords(coords_file, tmp_path / "render.log") == 0
    assert coords_file.stat().st_mtime_ns == before


def test_master_cache_key_is_content_based_and_versioned(tmp_path: Path, monkeypatch):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"same master")
    second.write_bytes(b"same master")
    key = MuseTalkMLXEngine._cache_digest(first)
    assert MuseTalkMLXEngine._cache_digest(second) == key
    second.write_bytes(b"changed master")
    assert MuseTalkMLXEngine._cache_digest(second) != key
    assert MuseTalkMLXEngine._cache_digest(first, "tenant:a:sha") != MuseTalkMLXEngine._cache_digest(first, "tenant:b:sha")
    monkeypatch.setattr("app.engines.musetalk.settings", SimpleNamespace(musetalk_target_fps=30))
    assert MuseTalkMLXEngine._cache_digest(first) != key


def test_landmark_cache_reuse_rebuild_and_concurrent_first_use(tmp_path: Path, monkeypatch):
    engine = MuseTalkMLXEngine()
    video = tmp_path / "master.mp4"
    video.write_bytes(b"source")
    cache_dir = tmp_path / "cache"
    log = tmp_path / "render.log"
    calls = []

    def fake_run(cmd, cwd=None, log_file=None):
        calls.append(cmd)
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"normalized")
            return
        time.sleep(0.03)
        frames_dir = Path(cmd[-2])
        paths = [frames_dir / f"{i:08d}.png" for i in range(2)]
        for path in paths:
            path.write_bytes(b"frame")
        with Path(cmd[-1]).open("wb") as fh:
            pickle.dump({"coords": [(1, 2, 3, 4)] * 2, "frames": [str(p) for p in paths], "n": 2, "fps": 25}, fh)

    monkeypatch.setattr(engine, "_run", fake_run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: engine._prepare_master_cache(video, cache_dir, log), range(2)))
    assert sorted(result[2]["landmark_cache"] for result in results) == ["built", "hit"]
    assert len(calls) == 2
    coords = cache_dir / "coords.pkl"
    mtime = coords.stat().st_mtime_ns
    assert engine._prepare_master_cache(video, cache_dir, log)[2]["landmark_cache"] == "hit"
    assert coords.stat().st_mtime_ns == mtime

    (cache_dir / "frames" / "00000001.png").unlink()
    assert engine._prepare_master_cache(video, cache_dir, log)[2]["landmark_cache"] == "built"
    coords.write_bytes(b"broken")
    assert engine._prepare_master_cache(video, cache_dir, log)[2]["landmark_cache"] == "built"
    assert len(calls) == 6


def test_resident_material_disk_hit_and_corrupt_rebuild(tmp_path: Path):
    import cv2

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    frame = frames_dir / "00000000.png"
    cv2.imwrite(str(frame), np.zeros((16, 16, 3), dtype=np.uint8))
    coords_file = tmp_path / "coords.pkl"
    with coords_file.open("wb") as fh:
        pickle.dump({"coords": [(1, 1, 9, 9)], "frames": [str(frame)], "fps": 25}, fh)
    calls = []

    def runtime():
        instance = ResidentMuseTalkRuntime.__new__(ResidentMuseTalkRuntime)
        instance.variant = "q8"
        instance._materials = {}
        instance.last_material_cache_status = "unprepared"
        instance.cv2 = cv2
        instance.mx = SimpleNamespace(float16=np.float16)
        instance.pipe = SimpleNamespace(get_latents_for_unet=lambda image: calls.append(1) or np.ones((1, 2), dtype=np.float16))
        instance._exact_blend_mask = lambda frame, box, mode: (np.ones((16, 16), dtype=np.uint8), (0, 0, 16, 16))
        return instance

    first = runtime()
    first.prepare_master(coords_file, tmp_path)
    assert first.last_material_cache_status == "built"
    first.prepare_master(coords_file, tmp_path)
    assert first.last_material_cache_status == "memory"
    second = runtime()
    second.prepare_master(coords_file, tmp_path)
    assert second.last_material_cache_status == "disk"
    assert len(calls) == 1
    (tmp_path / "resident-q8-m10-jaw" / "latents-f16.npy").write_bytes(b"corrupt")
    third = runtime()
    third.prepare_master(coords_file, tmp_path)
    assert third.last_material_cache_status == "built"
    assert len(calls) == 2
