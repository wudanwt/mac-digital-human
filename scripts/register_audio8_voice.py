#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.tts import Audio8Config, Audio8ONNXTTS


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a reusable Audio8 voice profile")
    parser.add_argument("--name", required=True, help="stable local voice name, e.g. dan")
    parser.add_argument("--audio", required=True, type=Path, help="0.5-30s reference audio")
    parser.add_argument("--text", required=True, help="accurate transcript of the reference audio")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8024")
    args = parser.parse_args()

    provider = Audio8ONNXTTS(Audio8Config(base_url=args.url, voice=args.name))
    result = provider.register_voice(
        name=args.name,
        audio=args.audio,
        text=args.text,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
