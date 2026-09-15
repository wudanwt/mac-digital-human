"""CosyVoice 2 zero-shot high-fidelity voice clone TTS provider."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .base import TTSError, TTSProvider

logger = logging.getLogger("mac_digital_human.tts.cosyvoice")


@dataclass(frozen=True)
class CosyVoiceConfig:
    bundle_dir: str | None = None
    voice: str = "default"
    ref_audio: str | None = None
    ref_text: str | None = None
    instruct: str | None = None
    speed: float = 1.0
    pause_seconds: float = 0.22


class CosyVoiceTTS:
    """Production CosyVoice 2 TTS engine.

    Heavy runtime libraries stay lazily imported so the SaaS API/control plane
    can import profile/registry code without installing the entire ML stack.
    """

    name = "cosyvoice2"
    _shared_service = None
    _shared_bundle_dir = None

    def __init__(self, config: CosyVoiceConfig | None = None) -> None:
        self.config = config or CosyVoiceConfig()
        root = Path(__file__).resolve().parents[2]
        self.bundle_dir = Path(
            self.config.bundle_dir
            or os.getenv("COSYVOICE_BUNDLE_DIR", str(root / "digital-human-tts"))
        ).resolve()
        default_ref_dir = self.bundle_dir / "voices" / "wudan"
        self._default_ref_audio = default_ref_dir / "reference.wav"
        self._default_ref_text = "今天欢迎来到会议的现场，我很开心，也很荣幸的给大家介绍我们最新的产品。"

    def _get_service(self):
        if CosyVoiceTTS._shared_service is not None and CosyVoiceTTS._shared_bundle_dir == str(self.bundle_dir):
            return CosyVoiceTTS._shared_service

        logger.info("Loading CosyVoice 2.0 0.5B model from: %s", self.bundle_dir)
        sys.path.insert(0, str(self.bundle_dir))
        try:
            from tts_core.service import CosyVoiceService

            CosyVoiceTTS._shared_service = CosyVoiceService(
                self.bundle_dir,
                pause_seconds=self.config.pause_seconds,
            )
            CosyVoiceTTS._shared_bundle_dir = str(self.bundle_dir)
            return CosyVoiceTTS._shared_service
        except Exception as exc:
            logger.error("Failed to load CosyVoice model: %s", exc)
            raise TTSError(f"CosyVoice engine initialization failed: {exc}") from exc

    def readiness(self) -> dict:
        model_path = self.bundle_dir / "models" / "CosyVoice2-0.5B"
        return {
            "provider": self.name,
            "ready": model_path.exists() and (model_path / "flow.pt").exists(),
            "bundle_dir": str(self.bundle_dir),
            "model_path": str(model_path),
            "model_installed": model_path.exists(),
            "warm": CosyVoiceTTS._shared_service is not None,
        }

    def synthesize(self, text: str, output: Path, **kwargs) -> Path:
        clean_text = text.strip()
        if not clean_text:
            raise TTSError("text is empty for synthesis")

        try:
            import soundfile as sf
        except ImportError as exc:
            raise TTSError("CosyVoice runtime requires soundfile; install .[cosyvoice]") from exc

        out_path = Path(output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ref_audio = kwargs.get("ref_audio") or self.config.ref_audio
        ref_text = kwargs.get("ref_text") or self.config.ref_text
        instruct = kwargs.get("instruct") or self.config.instruct
        speed = float(kwargs.get("speed") or self.config.speed or 1.0)

        resolved_ref_audio = None
        if ref_audio:
            p = Path(ref_audio).resolve()
            if p.exists():
                resolved_ref_audio = p
            else:
                p_rel = self.bundle_dir / ref_audio
                if p_rel.exists():
                    resolved_ref_audio = p_rel

        if not resolved_ref_audio:
            resolved_ref_audio = self._default_ref_audio
            if not ref_text:
                ref_text = self._default_ref_text

        if not resolved_ref_audio.exists():
            raise TTSError(f"Reference voice audio not found: {resolved_ref_audio}")

        if not ref_text or not ref_text.strip():
            txt_candidate = resolved_ref_audio.with_suffix(".txt")
            if txt_candidate.exists():
                ref_text = txt_candidate.read_text(encoding="utf-8").strip()
            else:
                ref_text = self._default_ref_text

        service = self._get_service()
        try:
            result = service.synthesize(
                text=clean_text,
                reference_audio=str(resolved_ref_audio),
                reference_text=ref_text.strip(),
                speed=speed,
                instruct=instruct,
            )
            sf.write(str(out_path), result.audio, result.sample_rate, subtype="PCM_16")
            return out_path
        except Exception as exc:
            logger.error("CosyVoice synthesis failed: %s", exc)
            raise TTSError(f"CosyVoice synthesis failed: {exc}") from exc

    def release(self) -> None:
        CosyVoiceTTS._shared_service = None
        CosyVoiceTTS._shared_bundle_dir = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
