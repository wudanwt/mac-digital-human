#!/usr/bin/env python3
"""CLI entrypoint to produce digital human micro-courses from PPT and scripts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.lecture import LecturePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce a digital human micro-course from a PPTX or PDF file.")
    parser.add_argument("ppt", help="Path to .pptx or .pdf presentation file.")
    parser.add_argument("--profile", "-p", default="dan", help="Avatar profile ID (default: dan).")
    parser.add_argument("--manifest", "-m", help="Optional JSON manifest file with slide script/layout overrides.")
    parser.add_argument("--output", "-o", help="Optional output MP4 video path.")
    parser.add_argument("--bgm", help="Optional background music audio file.")
    args = parser.parse_args()

    ppt_path = Path(args.ppt).resolve()
    if not ppt_path.exists():
        print(f"[ERROR] PPT file not found: {ppt_path}", file=sys.stderr)
        return 1

    overrides = {}
    if args.manifest:
        man_path = Path(args.manifest).resolve()
        if man_path.exists():
            overrides = json.loads(man_path.read_text(encoding="utf-8"))

    if args.profile:
        overrides.setdefault("profile", args.profile)
    if args.bgm:
        overrides["bgm"] = args.bgm

    print(f"🎬 开始制作微课: {ppt_path.name}")
    print(f"👤 讲师 Profile: {overrides.get('profile')}")

    pipeline = LecturePipeline()
    try:
        out_dir = Path(args.output).parent if args.output else None
        res = pipeline.build_from_ppt(ppt_path, manifest_override=overrides, output_dir=out_dir)
        print("\n✅ 微课制作完成！")
        print(f"📁 最终视频: {res.output_video}")
        print(f"📝 外挂字幕: {res.srt_path}")
        print(f"⏱️ 视频总长: {res.total_duration_seconds} 秒 (渲染用时: {res.elapsed_seconds} 秒)")
        print(f"📊 幻灯片页数: {len(res.slides)}")
        for s in res.slides:
            print(f"   - Slide {s.index:02d} [{s.layout}]: {s.title} ({s.duration_seconds}s)")
        return 0
    except Exception as exc:
        print(f"\n❌ 微课制作失败: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
