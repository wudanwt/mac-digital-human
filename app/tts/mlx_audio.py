from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

from .base import TTSError


@dataclass(frozen=True)
class TTSConfig:
    model: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
    voice: str = "Dylan"
    language: str = "Chinese"
    instruct: str = "Natural, clear, professional Mandarin delivery for enterprise training."
    clone_model: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
    ref_audio: str | None = None
    ref_text: str | None = None


class MLXAudioTTS:
    """Premium Qwen3-TTS adapter around Blaizzy/mlx-audio."""

    name = "qwen3"

    def __init__(self, config: TTSConfig | None = None) -> None:
        self.config = config or TTSConfig()
        self._model = None
        self._loaded_model_id: str | None = None

    def readiness(self) -> dict:
        try:
            import mlx_audio  # noqa: F401

            installed = True
        except Exception:
            installed = False
        return {
            "provider": self.name,
            "ready": installed,
            "model": self.config.model,
            "clone_model": self.config.clone_model,
            "voice": self.config.voice,
            "clone_enabled": bool(self.config.ref_audio),
        }

    def release(self) -> None:
        self._model = None
        self._loaded_model_id = None
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:
            pass

    def _load(self, model_id: str):
        if self._model is not None and self._loaded_model_id == model_id:
            return self._model
        if self._model is not None:
            self.release()
        try:
            from mlx_audio.tts.utils import load_model
        except Exception as exc:  # pragma: no cover - depends on optional local install
            raise TTSError("mlx-audio is not installed; run: bash scripts/setup_qwen3_tts.sh") from exc
        self._model = load_model(model_id)
        self._loaded_model_id = model_id
        return self._model

    def synthesize(
        self,
        text: str,
        output: Path,
        *,
        voice: str | None = None,
        language: str | None = None,
        instruct: str | None = None,
        ref_audio: Path | None = None,
        ref_text: str | None = None,
    ) -> Path:
        if not text.strip():
            raise TTSError("TTS text must not be empty")

        selected_ref_audio = ref_audio or (Path(self.config.ref_audio).expanduser() if self.config.ref_audio else None)
        selected_ref_text = ref_text or self.config.ref_text
        output.parent.mkdir(parents=True, exist_ok=True)

        if selected_ref_audio:
            if not selected_ref_audio.exists():
                raise TTSError(f"reference audio not found: {selected_ref_audio}")
            if not selected_ref_text:
                raise TTSError("voice cloning requires the transcript of the reference audio (ref_text)")
            model = self._load(self.config.clone_model)
            results = list(
                model.generate(
                    text=text,
                    ref_audio=str(selected_ref_audio),
                    ref_text=selected_ref_text,
                )
            )
        else:
            model = self._load(self.config.model)
            selected_voice = voice or self.config.voice
            selected_language = language or self.config.language
            selected_instruct = instruct if instruct is not None else self.config.instruct
            if hasattr(model, "generate_custom_voice"):
                results = list(
                    model.generate_custom_voice(
                        text=text,
                        speaker=selected_voice,
                        language=selected_language,
                        instruct=selected_instruct,
                    )
                )
            else:
                results = list(
                    model.generate(
                        text=text,
                        voice=selected_voice,
                        lang_code=selected_language,
                    )
                )

        if not results:
            raise TTSError("TTS returned no audio")

        try:
            import mlx.core as mx
            import numpy as np
            from mlx_audio.audio_io import write as audio_write
        except Exception as exc:  # pragma: no cover - optional local install
            raise TTSError("mlx-audio runtime dependencies are incomplete") from exc

        chunks = [np.asarray(item.audio, dtype=np.float32) for item in results]
        sample_rates = {int(item.sample_rate) for item in results}
        if len(sample_rates) != 1:
            raise TTSError(f"TTS returned mixed sample rates: {sorted(sample_rates)}")
        sample_rate = sample_rates.pop()
        waveform = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)
        audio_write(str(output), waveform, sample_rate, format="wav")
        mx.clear_cache()
        return output
