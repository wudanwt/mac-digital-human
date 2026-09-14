#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.course import CoursePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a complete digital-human course from a JSON manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = CoursePipeline().build(args.manifest, output=args.output)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
