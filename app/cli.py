from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from .config import settings
from .engines import LongCatMLXEngine, MuseTalkMLXEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Local digital-human generation on Apple Silicon")
    parser.add_argument("--engine", choices=["musetalk", "longcat"], default="musetalk")
    parser.add_argument("--audio", required=True, type=Path, help="driving audio")
    parser.add_argument("--video", type=Path, help="MuseTalk master video")
    parser.add_argument("--image", type=Path, help="LongCat reference image")
    parser.add_argument("--prompt", default=settings.longcat_default_prompt, help="LongCat scene / behavior prompt")
    parser.add_argument("--variant", default=None, help="engine model variant")
    parser.add_argument("--height", type=int, default=settings.longcat_height)
    parser.add_argument("--width", type=int, default=settings.longcat_width)
    parser.add_argument("--num-frames", type=int, default=settings.longcat_num_frames)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    console = Console()

    if args.engine == "musetalk":
        if args.video is None:
            parser.error("--video is required when --engine musetalk")
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
    else:
        if args.image is None:
            parser.error("--image is required when --engine longcat")
        variant = args.variant or settings.default_longcat_variant
        if variant not in {"q4-merged", "q8-merged", "merged"}:
            parser.error("LongCat --variant must be q4-merged, q8-merged or merged")

        engine = LongCatMLXEngine()
        status = engine.readiness(variant)
        if not status["ready"]:
            missing = [k for k, ok in status["checks"].items() if not ok]
            console.print("[red]LongCat 引擎尚未准备好：[/red] " + ", ".join(missing))
            console.print("先运行: bash scripts/setup_longcat.sh")
            raise SystemExit(2)

        console.print(
            f"[bold]LongCat Avatar 1.5 MLX[/bold] variant={variant} "
            f"size={args.width}x{args.height} frames={args.num_frames}"
        )
        result = engine.render(
            args.image,
            args.audio,
            prompt=args.prompt,
            variant=variant,
            height=args.height,
            width=args.width,
            num_frames=args.num_frames,
            seed=args.seed,
            output=args.output,
        )

    console.print(f"[green]完成[/green] {result.output}")
    console.print(f"引擎: {result.engine}")
    console.print(f"耗时: {result.elapsed_seconds:.1f}s")


if __name__ == "__main__":
    main()
