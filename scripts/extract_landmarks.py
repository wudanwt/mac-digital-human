"""DWPose + S3FD crop extraction, preferring Apple GPU.

Vendor extract_landmarks.py hardcodes CPU. rtmlib already maps device="mps"
to CoreMLExecutionProvider; PyTorch S3FD can run on MPS after allowing that
device. CLI is identical: extract_landmarks.py <video> <frames_dir> <coords.pkl>

Set EXTRACT_DEVICE=cpu to force the CPU path.
"""
from __future__ import annotations

import os
import pickle
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MLX = ROOT / "vendor" / "musetalk-mlx"
sys.path.insert(0, str(MLX / "refs" / "MuseTalk" / "musetalk" / "utils"))

from face_detection import FaceAlignment, LandmarksType  # noqa: E402
from face_detection.detection.core import FaceDetector  # noqa: E402
from rtmlib import Wholebody  # noqa: E402

COORD_PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)


def _forced_device() -> str | None:
    value = os.environ.get("EXTRACT_DEVICE", "").strip().lower()
    return value if value in {"cpu", "mps"} else None


def pose_device() -> str:
    forced = _forced_device()
    if forced:
        return forced
    try:
        import onnxruntime as ort

        if "CoreMLExecutionProvider" in ort.get_available_providers():
            return "mps"
    except Exception:
        pass
    return "cpu"


def s3fd_device() -> str:
    forced = _forced_device()
    if forced:
        return forced
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def allow_s3fd_mps() -> None:
    """Upstream FaceDetector only accepts cpu/cuda; MPS uses the same .to(device) path."""

    def _init(self, device, verbose):
        self.device = device
        self.verbose = verbose

    FaceDetector.__init__ = _init


def main() -> None:
    video, frames_dir, coords_pkl = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(frames_dir, exist_ok=True)

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    paths: list[str] = []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        path = os.path.join(frames_dir, f"{i:08d}.png")
        cv2.imwrite(path, fr)
        paths.append(path)
        i += 1
    cap.release()
    print(f"extracted {len(paths)} frames @ {fps:.2f} fps", flush=True)

    det_device = s3fd_device()
    kpt_device = pose_device()
    if det_device == "mps":
        allow_s3fd_mps()
    print(f"devices: dwpose={kpt_device} s3fd={det_device}", flush=True)

    dw = MLX / "weights" / "dwpose"
    pose = Wholebody(
        det=str(dw / "yolox_l.onnx"),
        pose=str(dw / "dw-ll_ucoco_384.onnx"),
        pose_input_size=(288, 384),
        backend="onnxruntime",
        device=kpt_device,
    )
    fa = FaceAlignment(LandmarksType._2D, flip_input=False, device=det_device)

    coords = []
    started = time.time()
    for idx, path in enumerate(paths):
        frame = cv2.imread(path)
        kpts, _ = pose(frame)
        bbox = fa.get_detections_for_batch(np.asarray([frame]))[0]
        if bbox is None or len(kpts) == 0:
            coords.append(COORD_PLACEHOLDER)
        else:
            flm = kpts[0][23:91].astype(np.int32)
            half = flm[29].copy()
            half_dist = np.max(flm[:, 1]) - half[1]
            upper = max(0, half[1] - half_dist)
            fl = (np.min(flm[:, 0]), int(upper), np.max(flm[:, 0]), np.max(flm[:, 1]))
            x1, y1, x2, y2 = fl
            coords.append(tuple(bbox) if (y2 - y1 <= 0 or x2 - x1 <= 0 or x1 < 0) else fl)
        if idx == 0 or (idx + 1) % 10 == 0 or idx + 1 == len(paths):
            elapsed = time.time() - started
            rate = (idx + 1) / elapsed if elapsed else 0
            print(
                f"detect {idx + 1}/{len(paths)} ({rate:.2f} fps, {elapsed:.0f}s)",
                flush=True,
            )

    with open(coords_pkl, "wb") as f:
        pickle.dump({"coords": coords, "fps": fps, "frames": paths, "n": len(paths)}, f)
    n_ok = sum(1 for c in coords if c != COORD_PLACEHOLDER)
    print(f"saved {len(coords)} coords ({n_ok} with face) -> {coords_pkl}", flush=True)


if __name__ == "__main__":
    main()
