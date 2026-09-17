"""CosyVoice 2 zero-shot high-fidelity voice clone TTS provider."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

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
    pronunciation_replacements: Mapping[str, str] | None = None


def apply_pronunciation_replacements(text: str, replacements: Mapping[str, str] | None) -> str:
    """Apply opt-in, TTS-only pronunciation aliases without changing captions."""
    if not replacements:
        return text

    result = text
    for source, spoken_form in sorted(replacements.items(), key=lambda item: len(str(item[0])), reverse=True):
        source = str(source).strip()
        spoken_form = str(spoken_form).strip()
        if source and spoken_form:
            result = result.replace(source, spoken_form)
    return result


class CosyVoiceTTS:
    """Production CosyVoice 2 TTS engine.

    Heavy runtime libraries stay lazily imported so the SaaS API/control plane
    can import profile/registry code without installing the entire ML stack.
    """

    name = "cosyvoice2"
    _shared_service = None
    _shared_bundle_dir = None
    # CosyVoice's model/frontend objects are shared to keep the 0.5B model warm.
    # Protect them from concurrent inference calls from future workers/prefetchers.
    _inference_lock = threading.RLock()

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
        self._normalized_ref_source: Path | None = None
        self._normalized_ref_audio: Path | None = None

    def _normalize_reference_audio(self, source: Path, target_dir: Path) -> Path:
        """Always standardize clone audio to the local pipeline's 24 kHz mono WAV contract.

        The old local avatar workflow normalized *every* uploaded reference,
        including WAV files.  SaaS previously skipped conversion when the file
        already ended in ``.wav``; a 44.1/48 kHz stereo WAV could therefore take
        a different path from the proven local workflow.
        """
        source = source.resolve()
        if (
            self._normalized_ref_source == source
            and self._normalized_ref_audio is not None
            and self._normalized_ref_audio.exists()
        ):
            return self._normalized_ref_audio

        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f".{source.stem}-cosyvoice-24k.wav"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                str(target),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not target.exists():
            target.unlink(missing_ok=True)
            detail = proc.stderr.strip() or "unknown FFmpeg error"
            raise TTSError(f"Reference voice audio conversion failed: {detail}")

        self._normalized_ref_source = source
        self._normalized_ref_audio = target
        return target

    def _get_service(self):
        if CosyVoiceTTS._shared_service is not None and CosyVoiceTTS._shared_bundle_dir == str(self.bundle_dir):
            service = CosyVoiceTTS._shared_service
            service.pause_seconds = self.config.pause_seconds
            return service

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

        spoken_text = apply_pronunciation_replacements(
            clean_text,
            kwargs.get("pronunciation_replacements") or self.config.pronunciation_replacements,
        )
        if spoken_text != clean_text:
            logger.info("Applied configured pronunciation replacements before CosyVoice synthesis")

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

        resolved_ref_audio = self._normalize_reference_audio(resolved_ref_audio, out_path.parent)
        try:
            info = sf.info(str(resolved_ref_audio))
            prompt_seconds = float(info.frames) / float(info.samplerate) if info.samplerate else 0.0
        except Exception as exc:
            raise TTSError(f"Reference voice audio cannot be inspected: {exc}") from exc
        if prompt_seconds < 1.0:
            raise TTSError("Reference voice audio is too short; record at least 3-5 seconds of clear speech")
        if prompt_seconds > 30.0:
            raise TTSError("Reference voice audio is longer than 30 seconds; CosyVoice zero-shot supports at most 30 seconds")
        if prompt_seconds > 15.0:
            logger.warning(
                "Long CosyVoice prompt (%.1fs). A clean 5-10s prompt with an exact transcript is usually more stable.",
                prompt_seconds,
            )

        service = self._get_service()
        try:
            with CosyVoiceTTS._inference_lock:
                service.pause_seconds = self.config.pause_seconds
                result = service.synthesize(
                    text=spoken_text,
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
