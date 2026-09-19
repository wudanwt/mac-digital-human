from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

from ..config import settings
from .auxiliary_task_models import AuxiliaryTaskLease
from .database import SessionLocal
from .models import Asset, Course, VoiceProfile
from .services import audit, enforce_storage_limit
from .speech_preview_models import SpeechPreviewJob
from .speech_preview_service import synthesis_fingerprint
from .storage import object_store
from .tts_pipeline import build_course_tts, synthesize_course_audio


log = logging.getLogger("digital-human.saas.speech-preview")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recover_stale_speech_previews() -> int:
    cutoff = _now() - timedelta(minutes=10)
    with SessionLocal() as db:
        result = db.execute(
            update(SpeechPreviewJob)
            .where(
                SpeechPreviewJob.status == "running",
                SpeechPreviewJob.updated_at < cutoff,
                ~select(AuxiliaryTaskLease.id).where(
                    AuxiliaryTaskLease.kind == "speech_preview",
                    AuxiliaryTaskLease.job_id == SpeechPreviewJob.id,
                    AuxiliaryTaskLease.expires_at > _now(),
                ).exists(),
            )
            .values(status="queued", progress=0, stage="recovered", started_at=None, updated_at=_now())
        )
        db.commit()
        return int(result.rowcount or 0)


def _claim_job() -> str | None:
    with SessionLocal() as db:
        query = (
            select(SpeechPreviewJob)
            .where(SpeechPreviewJob.status == "queued")
            .order_by(SpeechPreviewJob.created_at.asc())
            .limit(1)
        )
        try:
            query = query.with_for_update(skip_locked=True)
        except Exception:
            pass
        job = db.scalar(query)
        if job is None:
            return None
        job.status = "running"
        job.progress = 5
        job.stage = "preparing"
        job.error = None
        job.started_at = _now()
        job.updated_at = _now()
        db.commit()
        return job.id


def _mark_failed(job_id: str, exc: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(SpeechPreviewJob, job_id)
        if job and job.status not in {"canceled", "succeeded"}:
            job.status = "failed"
            job.progress = 100
            job.stage = "failed"
            job.error = str(exc)
            job.completed_at = _now()
            job.updated_at = _now()
            db.commit()


def _remove_older_previews(db, current: SpeechPreviewJob) -> None:
    older = db.scalars(
        select(SpeechPreviewJob).where(
            SpeechPreviewJob.id != current.id,
            SpeechPreviewJob.tenant_id == current.tenant_id,
            SpeechPreviewJob.course_id == current.course_id,
            SpeechPreviewJob.slide_index == current.slide_index,
            SpeechPreviewJob.scope == current.scope,
            SpeechPreviewJob.status.not_in(["queued", "running"]),
        )
    ).all()
    for item in older:
        asset = db.get(Asset, item.audio_asset_id) if item.audio_asset_id else None
        if asset and asset.kind == "audio_preview":
            object_store.delete(asset.object_key)
            db.delete(item)
            db.flush()
            db.delete(asset)
        else:
            db.delete(item)


def process_one_speech_preview() -> bool:
    job_id = _claim_job()
    if not job_id:
        return False

    work = settings.workspace_dir / "saas-speech-previews" / job_id
    work.mkdir(parents=True, exist_ok=True)
    created_key: str | None = None
    try:
        with SessionLocal() as db:
            job = db.get(SpeechPreviewJob, job_id)
            if job is None or job.status != "running":
                return True
            course = db.scalar(
                select(Course).where(Course.id == job.course_id, Course.tenant_id == job.tenant_id)
            )
            voice = db.scalar(
                select(VoiceProfile).where(
                    VoiceProfile.id == job.voice_profile_id,
                    VoiceProfile.tenant_id == job.tenant_id,
                )
            )
            if course is None or voice is None or not voice.reference_asset_id:
                raise RuntimeError("Course or voice was removed before speech preview started")
            reference = db.scalar(
                select(Asset).where(
                    Asset.id == voice.reference_asset_id,
                    Asset.tenant_id == job.tenant_id,
                    Asset.kind == "audio",
                )
            )
            if reference is None:
                raise RuntimeError("Voice reference audio is unavailable")
            course_settings = json.loads(course.settings_json or "{}")
            current_hash = synthesis_fingerprint(
                text=job.text,
                scope=job.scope,
                voice=voice,
                course_settings=course_settings,
            )
            if current_hash != job.text_hash:
                job.status = "canceled"
                job.progress = 100
                job.stage = "superseded"
                job.error = "Voice or course speech settings changed; preview again"
                job.completed_at = _now()
                job.updated_at = _now()
                db.commit()
                return True
            suffix = Path(reference.name).suffix.lower() or ".wav"
            ref_path = object_store.materialize(reference.object_key, work / f"reference{suffix}")

        runtime = build_course_tts(
            voice,
            ref_audio=ref_path,
            course_settings=course_settings,
            base=work,
        )
        target = synthesize_course_audio(runtime, job.text, work / "preview.wav")

        with SessionLocal() as db:
            job = db.get(SpeechPreviewJob, job_id)
            if job is None or job.status != "running":
                return True
            enforce_storage_limit(db, job.tenant_id, incoming_bytes=target.stat().st_size)
            key = f"{job.tenant_id}/speech-previews/{job.course_id}/{job.id}/{uuid4().hex}.wav"
            uri = object_store.put_file(target, key)
            created_key = key
            asset = Asset(
                tenant_id=job.tenant_id,
                user_id=job.user_id,
                kind="audio_preview",
                name=f"course-{job.course_id}-slide-{job.slide_index}-{job.scope}.wav",
                object_key=key,
                uri=uri,
                content_type="audio/wav",
                size_bytes=target.stat().st_size,
                sha256=_sha256(target),
                status="ready",
            )
            db.add(asset)
            db.flush()
            job.audio_asset_id = asset.id
            job.status = "succeeded"
            job.progress = 100
            job.stage = "completed"
            job.error = None
            job.completed_at = _now()
            job.updated_at = _now()
            _remove_older_previews(db, job)
            audit(
                db,
                action="course.speech_preview.completed",
                tenant_id=job.tenant_id,
                user_id=job.user_id,
                target_type="course",
                target_id=job.course_id,
                details={
                    "job_id": job.id,
                    "slide_index": job.slide_index,
                    "scope": job.scope,
                    "audio_asset_id": asset.id,
                },
            )
            db.commit()
        log.info("Speech preview completed job=%s slide=%s scope=%s", job_id, job.slide_index, job.scope)
    except Exception as exc:  # noqa: BLE001
        log.exception("Speech preview failed job=%s", job_id)
        if created_key:
            try:
                object_store.delete(created_key)
            except Exception:
                pass
        _mark_failed(job_id, exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return True
