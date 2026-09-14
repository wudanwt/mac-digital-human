#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import platform

from app.engines import LongCatMLXEngine, MuseTalkMLXEngine


def show_imports() -> None:
    print(f"Machine: {platform.machine()} / {platform.platform()}")
    for name in [
        "mlx",
        "torch",
        "onnxruntime",
        "rtmlib",
        "cv2",
        "transformers",
        "librosa",
        "imageio",
    ]:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, "__version__", "ok")
            print(f"{name}: {version}")
        except Exception as exc:
            print(f"{name}: IMPORT FAILED: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["all", "musetalk", "longcat"], default="all")
    parser.add_argument("--variant", choices=["q4", "q8", "fp16"], default="q8")
    parser.add_argument(
        "--longcat-variant",
        choices=["q4-merged", "q8-merged", "merged"],
        default="q4-merged",
    )
    args = parser.parse_args()

    show_imports()
    statuses: dict[str, dict] = {}
    if args.engine in {"all", "musetalk"}:
        statuses["musetalk"] = MuseTalkMLXEngine().readiness(args.variant)
    if args.engine in {"all", "longcat"}:
        statuses["longcat"] = LongCatMLXEngine().readiness(args.longcat_variant)

    print(json.dumps(statuses, ensure_ascii=False, indent=2))
    return 0 if all(status["ready"] for status in statuses.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
