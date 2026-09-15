#!/usr/bin/env python3
"""Download CosyVoice 2.0 0.5B high-fidelity voice cloning model weights."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TTS_MODEL_DIR = ROOT / "digital-human-tts" / "models" / "CosyVoice2-0.5B"


def is_model_complete(model_dir: Path) -> bool:
    if not model_dir.exists():
        return False
    required_files = [
        "cosyvoice2.yaml",
        "speech_tokenizer_v2.onnx",
    ]
    return all((model_dir / f).exists() for f in required_files)


def download_from_modelscope(target_dir: Path) -> bool:
    print(f"[cosyvoice2] 尝试通过 ModelScope 下载 iic/CosyVoice2-0.5B 到 {target_dir}...")
    try:
        from modelscope import snapshot_download
        snapshot_download("iic/CosyVoice2-0.5B", local_dir=str(target_dir))
        return is_model_complete(target_dir)
    except Exception as exc:
        print(f"[cosyvoice2] ModelScope 下载遇到异常: {exc}", file=sys.stderr)
        return False


def download_from_huggingface(target_dir: Path) -> bool:
    print(f"[cosyvoice2] 尝试通过 HuggingFace 下载 FunAudioLLM/CosyVoice2-0.5B 到 {target_dir}...")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download("FunAudioLLM/CosyVoice2-0.5B", local_dir=str(target_dir))
        return is_model_complete(target_dir)
    except Exception as exc:
        print(f"[cosyvoice2] HuggingFace 下载遇到异常: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Download CosyVoice 2.0 weights")
    parser.add_argument("--source", choices=["auto", "modelscope", "huggingface"], default="auto")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    args = parser.parse_args()

    if not args.force and is_model_complete(TTS_MODEL_DIR):
        print(f"[cosyvoice2] 模型权重已完整存在于: {TTS_MODEL_DIR}")
        return 0

    TTS_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    success = False
    if args.source in {"auto", "modelscope"}:
        success = download_from_modelscope(TTS_MODEL_DIR)

    if not success and args.source in {"auto", "huggingface"}:
        success = download_from_huggingface(TTS_MODEL_DIR)

    if not success:
        print(
            "[ERROR] CosyVoice 2.0 模型下载失败。您可以手动运行：\n"
            "  python -c \"from modelscope import snapshot_download; "
            f"snapshot_download('iic/CosyVoice2-0.5B', local_dir='{TTS_MODEL_DIR}')\"\n",
            file=sys.stderr,
        )
        return 1

    print(f"[cosyvoice2] 权重就绪: {TTS_MODEL_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
