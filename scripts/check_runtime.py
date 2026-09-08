#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import platform

from app.engine import MuseTalkMLXEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["q4", "q8", "fp16"], default="q8")
    args = parser.parse_args()

    print(f"Machine: {platform.machine()} / {platform.platform()}")
    for name in ["mlx", "torch", "onnxruntime", "rtmlib", "cv2"]:
        try:
            mod = importlib.import_module(name)
            version = getattr(mod, "__version__", "ok")
            print(f"{name}: {version}")
        except Exception as exc:
            print(f"{name}: IMPORT FAILED: {exc}")

    status = MuseTalkMLXEngine().readiness(args.variant)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
