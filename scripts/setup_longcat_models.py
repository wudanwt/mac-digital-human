#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "models" / "longcat"

VARIANTS = {
    "q4-merged": "mlx-community/LongCat-Video-Avatar-1.5-q4-dmd-merged",
    "q8-merged": "mlx-community/LongCat-Video-Avatar-1.5-q8-dmd-merged",
    "merged": "mlx-community/LongCat-Video-Avatar-1.5-bf16-dmd-merged",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download LongCat Avatar 1.5 MLX weights")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="q4-merged")
    args = parser.parse_args()

    repo_id = VARIANTS[args.variant]
    dirname = repo_id.split("/", 1)[1]
    target = TARGET_ROOT / dirname
    target.mkdir(parents=True, exist_ok=True)

    print(f"[longcat] downloading {repo_id}")
    print(f"[longcat] target: {target}")
    snapshot_download(repo_id=repo_id, local_dir=str(target))

    # The converted LongCat weights contain the Whisper encoder but not the
    # Transformers feature-extractor config used to build the 128-bin mel input.
    # Cache that tiny config now so normal inference can remain offline.
    whisper_fe = TARGET_ROOT / "whisper-large-v3-feature-extractor"
    whisper_fe.mkdir(parents=True, exist_ok=True)
    print("[longcat] caching Whisper-large-v3 feature extractor config")
    snapshot_download(
        repo_id="openai/whisper-large-v3",
        local_dir=str(whisper_fe),
        allow_patterns=["preprocessor_config.json"],
    )

    required = [
        target / "dit" / "config.json",
        target / "vae" / "config.json",
        target / "audio_encoder" / "config.json",
        target / "text_encoder" / "config.json",
        target / "tokenizer",
        whisper_fe / "preprocessor_config.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError("LongCat model download incomplete: " + ", ".join(missing))

    print("[longcat] model ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
