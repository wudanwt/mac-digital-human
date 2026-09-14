#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import mlx.core as mx
import numpy as np


def load_vendor_helpers(vendor: Path):
    """Load the pinned upstream run_inference helpers without modifying them."""
    script = vendor / "scripts" / "run_inference.py"
    if not script.exists():
        raise FileNotFoundError(f"LongCat MLX inference helper not found: {script}")

    sys.path.insert(0, str(vendor))
    spec = importlib.util.spec_from_file_location("longcat_mlx_run_inference", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import upstream helper: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_video_with_audio(frames: np.ndarray, audio: Path, out: Path, fps: int) -> None:
    import imageio.v2 as imageio

    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_name(out.stem + ".silent.mp4")
    writer = imageio.get_writer(str(silent), fps=fps, codec="libx264", quality=8)
    try:
        for frame in frames:
            writer.append_data(frame)
    finally:
        writer.close()

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(silent),
                "-i", str(audio),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(out),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        silent.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="LongCat Avatar 1.5 MLX custom-input adapter")
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--variant", choices=["q4-merged", "q8-merged", "merged"], default="q4-merged")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--num-frames", type=int, default=93)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if (args.num_frames - 1) % 4 != 0:
        raise SystemExit("--num-frames must satisfy 4n+1 (for example 93)")
    if args.height % 8 or args.width % 8:
        raise SystemExit("--height and --width must be divisible by 8")

    upstream = load_vendor_helpers(args.vendor)
    variant_dir = args.weights / upstream.VARIANT_DIRNAMES[args.variant]
    if not variant_dir.exists():
        raise SystemExit(f"weights not found: {variant_dir}")

    print("=== LongCat Avatar 1.5 MLX ===", flush=True)
    print(f"variant={args.variant} size={args.width}x{args.height} frames={args.num_frames} fps={args.fps}", flush=True)
    print(f"image={args.image}", flush=True)
    print(f"audio={args.audio}", flush=True)

    t0 = time.time()
    pipeline = upstream.build_pipeline(args.weights, variant=args.variant)
    print(f"pipeline loaded in {time.time() - t0:.1f}s", flush=True)

    image = upstream.preprocess_image(args.image, height=args.height, width=args.width)
    audio_mel = upstream.preprocess_audio_mel(args.audio)
    ids, mask = upstream.tokenize_prompt(args.prompt, variant_dir)

    text_hidden = pipeline.text_encoder(ids, mask=mask)
    text_embeds = text_hidden[:, None, :, :]
    text_mask = mask[:, None, None, :]

    # Keep parity with the upstream MLX smoke script for classifier-free guidance.
    empty_ids = mx.zeros_like(ids)
    empty_mask = mx.zeros_like(mask)
    uncond_hidden = pipeline.text_encoder(empty_ids, mask=empty_mask)
    uncond_embeds = uncond_hidden[:, None, :, :]
    uncond_mask = empty_mask[:, None, None, :]

    t1 = time.time()
    video = pipeline(
        image=image,
        audio_mel=audio_mel,
        text_embeds=text_embeds,
        text_mask=text_mask,
        uncond_embeds=uncond_embeds,
        uncond_mask=uncond_mask,
        height=args.height,
        width=args.width,
        num_frames=args.num_frames,
        seed=args.seed,
    )
    mx.eval(video)
    elapsed = time.time() - t1
    print(f"inference completed in {elapsed:.1f}s", flush=True)

    frames = (
        np.asarray(video).transpose(0, 2, 3, 4, 1)[0] * 127.5 + 127.5
    ).clip(0, 255).astype(np.uint8)
    write_video_with_audio(frames, args.audio, args.out, args.fps)
    print(f"WROTE {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
