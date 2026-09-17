from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Asset, VoiceProfile
from .speech_preview_models import SpeechPreviewJob


def synthesis_fingerprint(
    *,
    text: str,
    scope: str,
    voice: VoiceProfile,
    course_settings: dict[str, Any],
) -> str:
    """Hash only inputs that can change CosyVoice output."""
    payload = {
        "version": 1,
        "text": text.strip(),
        "scope": scope,
        "voice": {
            "id": voice.id,
            "provider": voice.provider,
            "reference_asset_id": voice.reference_asset_id,
            "transcript": voice.transcript,
            "settings": json.loads(voice.settings_json or "{}"),
            "updated_at": voice.updated_at.isoformat() if voice.updated_at else None,
        },
        "course_tts": {
            "speed": course_settings.get("speed", 1.0),
            "emotion": course_settings.get("emotion", "professional"),
            "tts": course_settings.get("tts") or {},
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reusable_page_preview(
    db: Session,
    *,
    tenant_id: str,
    course_id: str,
    slide_index: int,
    text: str,
    voice: VoiceProfile,
    course_settings: dict[str, Any],
) -> tuple[SpeechPreviewJob, Asset] | None:
    digest = synthesis_fingerprint(
        text=text,
        scope="page",
        voice=voice,
        course_settings=course_settings,
    )
    job = db.scalar(
        select(SpeechPreviewJob)
        .where(
            SpeechPreviewJob.tenant_id == tenant_id,
            SpeechPreviewJob.course_id == course_id,
            SpeechPreviewJob.slide_index == slide_index,
            SpeechPreviewJob.scope == "page",
            SpeechPreviewJob.text_hash == digest,
            SpeechPreviewJob.status == "succeeded",
            SpeechPreviewJob.audio_asset_id.is_not(None),
        )
        .order_by(SpeechPreviewJob.completed_at.desc())
        .limit(1)
    )
    if job is None or not job.audio_asset_id:
        return None
    asset = db.scalar(
        select(Asset).where(
            Asset.id == job.audio_asset_id,
            Asset.tenant_id == tenant_id,
            Asset.status == "ready",
        )
    )
    return (job, asset) if asset else None
