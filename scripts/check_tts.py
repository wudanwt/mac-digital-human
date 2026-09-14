#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from app.tts import create_tts


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local TTS providers")
    parser.add_argument("--provider", choices=["audio8", "qwen3", "all"], default="all")
    args = parser.parse_args()

    providers = ["audio8", "qwen3"] if args.provider == "all" else [args.provider]
    statuses = {name: create_tts({"provider": name}).readiness() for name in providers}
    print(json.dumps(statuses, ensure_ascii=False, indent=2))
    return 0 if all(item.get("ready") for item in statuses.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
