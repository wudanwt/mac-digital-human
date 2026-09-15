from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from .config import settings
from .engines import MuseTalkMLXEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Local digital-human generation on Apple Silicon")
    parser.add_argument("--audio", required=True, type=Path, help="driving audio")
    parser.add_argument("--video", required=True, type=Path, help="MuseTalk master video")
    parser.add_argument("--variant", default=None, help="engine model variant (q4, q8, fp16)")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    console = Console()

    variant = args.variant or settings.default_musetalk_variant
    if variant not in {"q4", "q8", "fp16"}:
        parser.error("MuseTalk --variant must be q4, q8 or fp16")

    engine = MuseTalkMLXEngine()
    status = engine.readiness(variant)
    if not status["ready"]:
        missing = [k for k, ok in status["checks"].items() if not ok]
        console.print("[red]MuseTalk 引擎尚未准备好：[/red] " + ", ".join(missing))
        console.print("先运行: bash scripts/setup.sh")
        raise SystemExit(2)

    console.print(f"[bold]MuseTalk-MLX[/bold] variant={variant}")
    result = engine.render(args.video, args.audio, variant=variant, output=args.output)

    console.print(f"[green]完成[/green] {result.output}")
    console.print(f"引擎: {result.engine}")
    console.print(f"耗时: {result.elapsed_seconds:.1f}s")


if __name__ == "__main__":
    main()

