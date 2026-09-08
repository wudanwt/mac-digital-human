#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import urlretrieve

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MLX = ROOT / "vendor" / "musetalk-mlx"
UPSTREAM = ROOT / "vendor" / "MuseTalk"


def download_face_parse() -> None:
    target = UPSTREAM / "models" / "face-parse-bisent"
    target.mkdir(parents=True, exist_ok=True)
    bisenet = target / "79999_iter.pth"
    resnet = target / "resnet18-5c106cde.pth"

    if not bisenet.exists():
        import gdown
        print("[models] face-parse-bisenet")
        ok = gdown.download(id="154JgKpzCPW82qINcVieuPH3fZ2e0P812", output=str(bisenet), quiet=False)
        if not ok:
            raise RuntimeError("failed to download face parsing checkpoint")
    if not resnet.exists():
        print("[models] resnet18")
        urlretrieve("https://download.pytorch.org/models/resnet18-5c106cde.pth", resnet)


def download_s3fd() -> None:
    target = UPSTREAM / "musetalk" / "utils" / "face_detection" / "detection" / "sfd" / "s3fd.pth"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print("[models] S3FD face detector")
    urlretrieve("https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth", target)


def download_dwpose() -> None:
    target = MLX / "weights" / "dwpose"
    target.mkdir(parents=True, exist_ok=True)
    print("[models] DWPose ONNX")
    snapshot_download(
        repo_id="yzd-v/DWPose",
        local_dir=str(target),
        allow_patterns=["dw-ll_ucoco_384.onnx", "yolox_l.onnx"],
    )
    required = [target / "dw-ll_ucoco_384.onnx", target / "yolox_l.onnx"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError("DWPose files missing after download: " + ", ".join(missing))


def download_mlx_variant(variant: str) -> None:
    repo_id = f"mlx-community/MuseTalk-1.5-{variant}"
    target = MLX / "dist" / f"MuseTalk-1.5-MLX-{variant}"
    target.mkdir(parents=True, exist_ok=True)
    print(f"[models] {repo_id} -> {target}")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        allow_patterns=["config.json", "*.safetensors", "README.md"],
    )
    required = ["config.json", "unet.safetensors", "vae.safetensors", "whisper_encoder.safetensors"]
    missing = [name for name in required if not (target / name).exists()]
    if missing:
        raise RuntimeError("MLX model files missing: " + ", ".join(missing))


def create_upstream_link() -> None:
    refs = MLX / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    link = refs / "MuseTalk"
    if link.is_symlink() or link.exists():
        return
    link.symlink_to(Path("../../MuseTalk"))
    print(f"[link] {link} -> ../../MuseTalk")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["q4", "q8", "fp16"], default="q8")
    args = parser.parse_args()

    if not MLX.exists() or not UPSTREAM.exists():
        print("vendor repositories not found; run bash scripts/setup.sh first", file=sys.stderr)
        return 2

    create_upstream_link()
    download_mlx_variant(args.variant)
    download_dwpose()
    download_face_parse()
    download_s3fd()
    print("[models] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
