from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from .engine import MuseTalkMLXEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a local digital-human lip-sync video on Apple Silicon")
    parser.add_argument("--video", required=True, type=Path, help="master video")
    parser.add_argument("--audio", required=True, type=Path, help="new driving audio")
    parser.add_argument("--variant", choices=["q4", "q8", "fp16"], default="q8")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    console = Console()
    engine = MuseTalkMLXEngine()
    status = engine.readiness(args.variant)
    if not status["ready"]:
        missing = [k for k, ok in status["checks"].items() if not ok]
        console.print("[red]引擎尚未准备好：[/red] " + ", ".join(missing))
        console.print("先运行: bash scripts/setup.sh")
        raise SystemExit(2)

    console.print(f"[bold]MuseTalk-MLX[/bold] variant={args.variant}")
    result = engine.render(args.video, args.audio, args.variant, args.output)
    console.print(f"[green]完成[/green] {result.output}")
    console.print(f"耗时: {result.elapsed_seconds:.1f}s")


if __name__ == "__main__":
    main()
