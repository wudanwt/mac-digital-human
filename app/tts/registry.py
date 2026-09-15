from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import TTSError, TTSProvider
from .cosyvoice import CosyVoiceConfig, CosyVoiceTTS


def _resolve_path(base: Path, value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return str(path)


def infer_provider(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("provider") or "").strip().lower()
    if explicit:
        aliases = {
            "cosyvoice": "cosyvoice2",
            "cosyvoice2": "cosyvoice2",
            "cosy": "cosyvoice2",
            # 兼容旧 profiles 自动迁移至 CosyVoice 2.0
            "audio8": "cosyvoice2",
            "audio8_onnx": "cosyvoice2",
            "onnx": "cosyvoice2",
            "mlx": "cosyvoice2",
            "mlx_audio": "cosyvoice2",
            "qwen": "cosyvoice2",
            "qwen3": "cosyvoice2",
        }
        if explicit not in aliases:
            raise TTSError(f"unsupported TTS provider: {explicit}")
        return aliases[explicit]

    return "cosyvoice2"


def create_tts(payload: dict[str, Any] | None = None, *, base: Path | None = None) -> TTSProvider:
    payload = dict(payload or {})
    base = (base or Path.cwd()).resolve()
    provider = infer_provider(payload)

    if provider == "cosyvoice2":
        ref_audio = _resolve_path(base, payload.get("ref_audio"))
        config = CosyVoiceConfig(
            bundle_dir=_resolve_path(base, payload.get("bundle_dir")),
            voice=str(payload.get("voice") or "wudan"),
            ref_audio=ref_audio,
            ref_text=payload.get("ref_text"),
            instruct=payload.get("instruct"),
            speed=float(payload.get("speed") or 1.0),
            pause_seconds=float(payload.get("pause_seconds") or 0.22),
        )
        return CosyVoiceTTS(config)

    raise TTSError(f"unsupported TTS provider: {provider}")
