from __future__ import annotations

from pathlib import Path
from typing import Any

from .audio8_onnx import Audio8Config, Audio8ONNXTTS
from .base import TTSError, TTSProvider
from .mlx_audio import MLXAudioTTS, TTSConfig


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
            "mlx": "qwen3",
            "mlx_audio": "qwen3",
            "qwen": "qwen3",
            "qwen3": "qwen3",
            "audio8": "audio8",
            "audio8_onnx": "audio8",
            "onnx": "audio8",
        }
        if explicit not in aliases:
            raise TTSError(f"unsupported TTS provider: {explicit}")
        return aliases[explicit]

    # Backward compatibility: old manifests named a Qwen model directly.
    model = str(payload.get("model") or "")
    if "Qwen3-TTS" in model or "qwen3-tts" in model.lower():
        return "qwen3"
    return "audio8"


def create_tts(payload: dict[str, Any] | None = None, *, base: Path | None = None) -> TTSProvider:
    payload = dict(payload or {})
    base = (base or Path.cwd()).resolve()
    provider = infer_provider(payload)

    if provider == "audio8":
        ref_audio = _resolve_path(base, payload.get("ref_audio"))
        config = Audio8Config(
            base_url=str(payload.get("base_url") or "http://127.0.0.1:8024"),
            voice=str(payload.get("voice") or payload.get("voice_profile") or "default"),
            runtime_dir=_resolve_path(base, payload.get("runtime_dir")),
            auto_start=bool(payload.get("auto_start", True)),
            threads=int(payload.get("threads", 5)),
            max_new_tokens=int(payload.get("max_new_tokens", 1024)),
            temperature=float(payload.get("temperature", 0.7)),
            top_p=float(payload.get("top_p", 0.9)),
            top_k=int(payload.get("top_k", 50)),
            seed=int(payload.get("seed", 42)),
            ref_audio=ref_audio,
            ref_text=payload.get("ref_text"),
            overwrite_voice=bool(payload.get("overwrite_voice", False)),
        )
        return Audio8ONNXTTS(config)

    defaults = TTSConfig()
    ref_audio = _resolve_path(base, payload.get("ref_audio"))
    config = TTSConfig(
        model=str(payload.get("model") or defaults.model),
        voice=str(payload.get("voice") or defaults.voice),
        language=str(payload.get("language") or defaults.language),
        instruct=str(payload.get("instruct") or defaults.instruct),
        clone_model=str(payload.get("clone_model") or defaults.clone_model),
        ref_audio=ref_audio,
        ref_text=payload.get("ref_text"),
    )
    return MLXAudioTTS(config)
