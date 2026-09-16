from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..tts import create_tts, infer_provider
from ..tts.base import TTSProvider
from .models import VoiceProfile


@dataclass(frozen=True)
class CourseTTSRuntime:
    provider: TTSProvider
    provider_name: str
    speed: float
    emotion: str
    emotion_label: str


def _clamp_speed(value: Any) -> float:
    try:
        speed = float(value or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    return max(0.75, min(1.35, speed))


def build_course_tts(
    voice: VoiceProfile,
    *,
    ref_audio: Path | None,
    course_settings: dict[str, Any],
    base: Path,
) -> CourseTTSRuntime:
    """Build the same production TTS configuration used by the local lecture pipeline.

    The SaaS control plane stores provider-specific settings on the voice profile and
    course-level delivery controls (speed/emotion) on the course.  This function
    deliberately mirrors ``app.lecture.LecturePipeline`` so local and SaaS renders
    do not drift in voice character or post-processing.
    """

    profile_settings = json.loads(voice.settings_json or "{}")
    course_tts = dict(course_settings.get("tts") or {})
    payload: dict[str, Any] = {**profile_settings, **course_tts}
    payload["provider"] = voice.provider
    payload["ref_audio"] = str(ref_audio) if ref_audio else None
    payload["ref_text"] = voice.transcript or None

    speed = _clamp_speed(course_settings.get("speed", payload.get("speed", 1.0)))
    emotion = str(course_settings.get("emotion") or payload.get("emotion") or "professional").strip().lower()
    payload["speed"] = speed
    provider_name = infer_provider(payload)

    emotion_label = "标准专业"
    if emotion == "passionate":
        payload.setdefault("temperature", 0.85)
        payload.setdefault("top_p", 0.95)
        payload.setdefault("instruct", "用激昂有力、富有感染力且充满热情的语气进行演讲授课<|endofprompt|>")
        payload.setdefault("pause_seconds", 0.18)
        emotion_label = "激昂有力"
    elif emotion == "warm":
        payload.setdefault("temperature", 0.75)
        payload.setdefault("top_p", 0.92)
        payload.setdefault("instruct", "用亲切温和、生动交流且通俗易懂的语气进行讲课<|endofprompt|>")
        payload.setdefault("pause_seconds", 0.24)
        emotion_label = "亲切温和"
    elif emotion == "calm":
        payload.setdefault("temperature", 0.60)
        payload.setdefault("top_p", 0.85)
        payload.setdefault("instruct", "用轻松自然、从容不迫、娓娓道来的语调进行讲解<|endofprompt|>")
        payload.setdefault("pause_seconds", 0.28)
        emotion_label = "从容淡雅"
    else:
        payload.setdefault("temperature", 0.65)
        payload.setdefault("top_p", 0.88)
        payload.setdefault("pause_seconds", 0.22)
        if provider_name == "cosyvoice2":
            # Keep professional zero-shot cloning pure.  The local production
            # pipeline intentionally removes instruct text here to avoid prompt
            # leakage into speech and to preserve the reference speaker identity.
            payload.pop("instruct", None)
        else:
            payload.setdefault("instruct", "用沉稳严谨、标准专业的大学讲师语气进行授课")

    provider = create_tts(payload, base=base)
    readiness = provider.readiness()
    if not readiness.get("ready", False):
        raise RuntimeError("TTS provider is not ready: " + json.dumps(readiness, ensure_ascii=False))

    return CourseTTSRuntime(
        provider=provider,
        provider_name=provider_name,
        speed=speed,
        emotion=emotion,
        emotion_label=emotion_label,
    )


def _ffmpeg_audio(source: Path, target: Path, filters: list[str]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source)]
    if filters:
        command.extend(["-af", ",".join(filters)])
    command.extend(["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target)])
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(proc.stderr.strip() or "FFmpeg audio normalization failed")
    return target


def synthesize_course_audio(runtime: CourseTTSRuntime, text: str, target: Path) -> Path:
    """Synthesize and normalize one slide exactly like the mature local pipeline."""

    target.parent.mkdir(parents=True, exist_ok=True)
    raw = target.with_name(f"{target.stem}_raw.wav")
    raw.unlink(missing_ok=True)
    runtime.provider.synthesize(text, raw)

    if runtime.provider_name == "cosyvoice2":
        # CosyVoice 2 already performs high-fidelity synthesis.  Keep only the
        # gentle cleanup/gain used in the local lecture pipeline.
        filters = ["highpass=f=60", "volume=1.05"]
    else:
        filters = ["highpass=f=80", "lowpass=f=7500", "afftdn=nf=-25"]
        if abs(runtime.speed - 1.0) > 0.03:
            filters.append(f"atempo={runtime.speed}")

    try:
        return _ffmpeg_audio(raw, target, filters)
    finally:
        raw.unlink(missing_ok=True)


def normalize_external_audio(source: Path, target: Path) -> Path:
    """Normalize uploaded/per-slide audio to the exact MuseTalk input contract."""

    return _ffmpeg_audio(source, target, [])
