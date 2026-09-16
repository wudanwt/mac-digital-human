from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .domain import RenderJob
from .models import Asset, Avatar, ConsentRecord, Course, RenderJobRecord, VoiceProfile
from .queue import job_queue
from .security import Principal, get_principal, require_admin
from .services import (
    audit,
    enforce_avatar_limit,
    estimate_script_seconds,
    plan_for_tenant,
    refund_render_seconds,
    reserve_render_seconds,
    utcnow,
)
from .settings import saas_settings


voice_router = APIRouter(prefix="/voices", tags=["voices"])
avatar_router = APIRouter(prefix="/avatars", tags=["avatars"])
course_router = APIRouter(prefix="/courses", tags=["courses"])
job_router = APIRouter(prefix="/jobs", tags=["jobs"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="cosyvoice", max_length=60)
    reference_asset_id: str | None = None
    transcript: str = Field(default="", max_length=10000)
    settings: dict[str, Any] = Field(default_factory=dict)
    consent_confirmed: bool = False


class VoiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    transcript: str | None = Field(default=None, min_length=1, max_length=10000)
    transcript_verified: bool | None = None


class AvatarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    image_asset_id: str | None = None
    master_video_asset_id: str | None = None
    voice_profile_id: str | None = None
    prompt: str = Field(default="", max_length=20000)
    consent_confirmed: bool = False


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    ppt_asset_id: str | None = None
    avatar_id: str | None = None
    voice_profile_id: str | None = None
    script: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    ppt_asset_id: str | None = None
    avatar_id: str | None = None
    voice_profile_id: str | None = None
    script: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None


class RenderRequest(BaseModel):
    engine: str = Field(default="musetalk", pattern="^(musetalk|mock)$")
    estimated_seconds: int = Field(default=60, ge=1, le=21600)
    audio_asset_id: str | None = None


def _tenant_asset(db: Session, tenant_id: str, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))
    if asset is None:
        raise HTTPException(status_code=422, detail=f"Asset {asset_id} is not available in this workspace")
    return asset


def _tenant_voice(db: Session, tenant_id: str, voice_id: str | None) -> VoiceProfile | None:
    if not voice_id:
        return None
    item = db.scalar(select(VoiceProfile).where(VoiceProfile.id == voice_id, VoiceProfile.tenant_id == tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return item


def _tenant_avatar(db: Session, tenant_id: str, avatar_id: str | None) -> Avatar | None:
    if not avatar_id:
        return None
    item = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return item


def _tenant_course(db: Session, tenant_id: str, course_id: str) -> Course:
    item = db.scalar(select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return item


def _can_manage_course(principal: Principal, course: Course) -> bool:
    return principal.is_superuser or principal.role in {"owner", "admin"} or course.user_id == principal.user_id


def _record_consent(
    db: Session,
    *,
    principal: Principal,
    subject_type: str,
    subject_id: str,
    consent_type: str,
    statement: str,
) -> None:
    db.add(
        ConsentRecord(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            subject_type=subject_type,
            subject_id=subject_id,
            consent_type=consent_type,
            statement=statement,
        )
    )
    audit(
        db,
        action="consent.accept",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type=subject_type,
        target_id=subject_id,
        details={"consent_type": consent_type, "statement": statement},
    )


def _voice_dict(item: VoiceProfile) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "provider": item.provider,
        "reference_asset_id": item.reference_asset_id,
        "transcript": item.transcript,
        "settings": json.loads(item.settings_json or "{}"),
        "created_at": item.created_at.isoformat(),
    }


def _avatar_dict(item: Avatar) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "image_asset_id": item.image_asset_id,
        "master_video_asset_id": item.master_video_asset_id,
        "voice_profile_id": item.voice_profile_id,
        "prompt": item.prompt,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


def _course_dict(item: Course) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "ppt_asset_id": item.ppt_asset_id,
        "avatar_id": item.avatar_id,
        "voice_profile_id": item.voice_profile_id,
        "status": item.status,
        "script": json.loads(item.script_json or "[]"),
        "settings": json.loads(item.settings_json or "{}"),
        "output_asset_id": item.output_asset_id,
        "output_download_url": (
            f"{saas_settings.api_prefix}/assets/{item.output_asset_id}/download" if item.output_asset_id else None
        ),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _job_dict(item: RenderJobRecord) -> dict:
    return {
        "id": item.id,
        "course_id": item.course_id,
        "engine": item.engine,
        "status": item.status,
        "progress": item.progress,
        "stage": item.stage,
        "output_uri": item.output_uri,
        "output_asset_id": item.output_asset_id,
        "output_download_url": (
            f"{saas_settings.api_prefix}/assets/{item.output_asset_id}/download" if item.output_asset_id else None
        ),
        "error": item.error,
        "estimated_seconds": item.estimated_seconds,
        "video_seconds": item.video_seconds,
        "gpu_seconds": item.gpu_seconds,
        "queue_wait_seconds": item.queue_wait_seconds,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@voice_router.get("")
def list_voices(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    items = db.scalars(
        select(VoiceProfile)
        .where(VoiceProfile.tenant_id == principal.tenant_id)
        .order_by(VoiceProfile.created_at.desc())
    ).all()
    return [_voice_dict(item) for item in items]


@voice_router.post("", status_code=201)
def create_voice(
    body: VoiceCreate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _tenant_asset(db, principal.tenant_id, body.reference_asset_id)
    if body.reference_asset_id and not body.consent_confirmed:
        raise HTTPException(status_code=422, detail="Voice cloning requires explicit consent confirmation")
    item = VoiceProfile(
        tenant_id=principal.tenant_id,
        name=body.name.strip(),
        provider=body.provider.strip().lower(),
        reference_asset_id=body.reference_asset_id,
        transcript=body.transcript,
        settings_json=json.dumps(body.settings, ensure_ascii=False),
    )
    db.add(item)
    db.flush()
    if body.reference_asset_id:
        _record_consent(
            db,
            principal=principal,
            subject_type="voice",
            subject_id=item.id,
            consent_type="voice_clone_authorization",
            statement="I confirm that I have authorization to use this voice recording for synthetic voice generation.",
        )
    audit(db, action="voice.create", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="voice", target_id=item.id)
    db.commit()
    return _voice_dict(item)


@voice_router.patch("/{voice_id}")
def update_voice(
    voice_id: str,
    body: VoiceUpdate,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = _tenant_voice(db, principal.tenant_id, voice_id)
    name_changed = False
    transcript_changed = False
    if body.name is not None:
        clean_name = body.name.strip()
        if not clean_name:
            raise HTTPException(status_code=422, detail="Voice name cannot be empty")
        name_changed = clean_name != item.name
        item.name = clean_name
    if body.transcript is not None:
        clean_transcript = body.transcript.strip()
        if not clean_transcript:
            raise HTTPException(status_code=422, detail="Reference recording transcript cannot be empty")
        transcript_changed = clean_transcript != item.transcript
        item.transcript = clean_transcript
    settings = json.loads(item.settings_json or "{}")
    if not isinstance(settings, dict):
        settings = {}
    if body.transcript_verified is not None:
        settings["transcript_verified"] = body.transcript_verified
    elif transcript_changed:
        settings["transcript_verified"] = False
    item.settings_json = json.dumps(settings, ensure_ascii=False)
    audit(
        db,
        action="voice.update",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="voice",
        target_id=item.id,
        details={"name_changed": name_changed, "transcript_changed": transcript_changed},
    )
    db.commit()
    return _voice_dict(item)


@voice_router.delete("/{voice_id}", status_code=204)
def delete_voice(
    voice_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    item = _tenant_voice(db, principal.tenant_id, voice_id)
    if db.scalar(select(Avatar.id).where(Avatar.tenant_id == principal.tenant_id, Avatar.voice_profile_id == voice_id).limit(1)):
        raise HTTPException(status_code=409, detail="Voice profile is referenced by an avatar")
    if db.scalar(select(Course.id).where(Course.tenant_id == principal.tenant_id, Course.voice_profile_id == voice_id).limit(1)):
        raise HTTPException(status_code=409, detail="Voice profile is referenced by a course")
    db.delete(item)
    audit(db, action="voice.delete", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="voice", target_id=voice_id)
    db.commit()


@avatar_router.get("")
def list_avatars(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    items = db.scalars(
        select(Avatar).where(Avatar.tenant_id == principal.tenant_id).order_by(Avatar.created_at.desc())
    ).all()
    return [_avatar_dict(item) for item in items]


@avatar_router.post("", status_code=201)
def create_avatar(
    body: AvatarCreate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _tenant_asset(db, principal.tenant_id, body.image_asset_id)
    _tenant_asset(db, principal.tenant_id, body.master_video_asset_id)
    _tenant_voice(db, principal.tenant_id, body.voice_profile_id)
    if not body.image_asset_id and not body.master_video_asset_id:
        raise HTTPException(status_code=422, detail="Avatar requires an image or master video asset")
    if not body.consent_confirmed:
        raise HTTPException(status_code=422, detail="Digital-human creation requires explicit portrait/video authorization")
    enforce_avatar_limit(db, principal.tenant_id)
    item = Avatar(
        tenant_id=principal.tenant_id,
        name=body.name.strip(),
        image_asset_id=body.image_asset_id,
        master_video_asset_id=body.master_video_asset_id,
        voice_profile_id=body.voice_profile_id,
        prompt=body.prompt,
    )
    db.add(item)
    db.flush()
    _record_consent(
        db,
        principal=principal,
        subject_type="avatar",
        subject_id=item.id,
        consent_type="portrait_synthesis_authorization",
        statement="I confirm that I have authorization to use this person's image/video for digital-human synthesis.",
    )
    audit(db, action="avatar.create", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="avatar", target_id=item.id)
    db.commit()
    return _avatar_dict(item)


@avatar_router.delete("/{avatar_id}", status_code=204)
def delete_avatar(
    avatar_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    item = _tenant_avatar(db, principal.tenant_id, avatar_id)
    if db.scalar(select(Course.id).where(Course.tenant_id == principal.tenant_id, Course.avatar_id == avatar_id).limit(1)):
        raise HTTPException(status_code=409, detail="Avatar is referenced by a course")
    db.delete(item)
    audit(db, action="avatar.delete", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="avatar", target_id=avatar_id)
    db.commit()


@course_router.get("")
def list_courses(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    items = db.scalars(
        select(Course).where(Course.tenant_id == principal.tenant_id).order_by(Course.updated_at.desc())
    ).all()
    return [_course_dict(item) for item in items]


@course_router.post("", status_code=201)
def create_course(
    body: CourseCreate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _tenant_asset(db, principal.tenant_id, body.ppt_asset_id)
    _tenant_avatar(db, principal.tenant_id, body.avatar_id)
    _tenant_voice(db, principal.tenant_id, body.voice_profile_id)
    item = Course(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        title=body.title.strip(),
        ppt_asset_id=body.ppt_asset_id,
        avatar_id=body.avatar_id,
        voice_profile_id=body.voice_profile_id,
        script_json=json.dumps(body.script, ensure_ascii=False),
        settings_json=json.dumps(body.settings, ensure_ascii=False),
    )
    db.add(item)
    db.flush()
    audit(db, action="course.create", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="course", target_id=item.id)
    db.commit()
    return _course_dict(item)


@course_router.get("/{course_id}")
def get_course(
    course_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return _course_dict(_tenant_course(db, principal.tenant_id, course_id))


@course_router.patch("/{course_id}")
def update_course(
    course_id: str,
    body: CourseUpdate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = _tenant_course(db, principal.tenant_id, course_id)
    if not _can_manage_course(principal, item):
        raise HTTPException(status_code=403, detail="You can only edit your own course")
    values = body.model_dump(exclude_unset=True)
    if "ppt_asset_id" in values:
        _tenant_asset(db, principal.tenant_id, values["ppt_asset_id"])
        item.ppt_asset_id = values["ppt_asset_id"]
    if "avatar_id" in values:
        _tenant_avatar(db, principal.tenant_id, values["avatar_id"])
        item.avatar_id = values["avatar_id"]
    if "voice_profile_id" in values:
        _tenant_voice(db, principal.tenant_id, values["voice_profile_id"])
        item.voice_profile_id = values["voice_profile_id"]
    if body.title is not None:
        item.title = body.title.strip()
    if body.script is not None:
        item.script_json = json.dumps(body.script, ensure_ascii=False)
    if body.settings is not None:
        item.settings_json = json.dumps(body.settings, ensure_ascii=False)
    audit(db, action="course.update", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="course", target_id=item.id)
    db.commit()
    return _course_dict(item)


@course_router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    item = _tenant_course(db, principal.tenant_id, course_id)
    if not _can_manage_course(principal, item):
        raise HTTPException(status_code=403, detail="You can only delete your own course")
    active_job = db.scalar(
        select(RenderJobRecord.id).where(
            RenderJobRecord.course_id == item.id,
            RenderJobRecord.status.in_(["queued", "running"]),
        ).limit(1)
    )
    if active_job:
        raise HTTPException(status_code=409, detail="Course has an active render job")
    db.delete(item)
    audit(db, action="course.delete", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="course", target_id=course_id)
    db.commit()


@course_router.post("/{course_id}/render", status_code=202)
def render_course(
    course_id: str,
    body: RenderRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course = _tenant_course(db, principal.tenant_id, course_id)
    if not _can_manage_course(principal, course):
        raise HTTPException(status_code=403, detail="You can only render your own course")
    avatar = _tenant_avatar(db, principal.tenant_id, course.avatar_id) if course.avatar_id else None
    voice = _tenant_voice(db, principal.tenant_id, course.voice_profile_id) if course.voice_profile_id else None
    ppt = _tenant_asset(db, principal.tenant_id, course.ppt_asset_id) if course.ppt_asset_id else None
    audio = _tenant_asset(db, principal.tenant_id, body.audio_asset_id) if body.audio_asset_id else None
    if ppt is None:
        raise HTTPException(status_code=422, detail="Select a PPT before rendering")
    if avatar is None:
        raise HTTPException(status_code=422, detail="Select an avatar before rendering")
    if avatar.master_video_asset_id is None and body.engine == "musetalk":
        raise HTTPException(status_code=422, detail="MuseTalk avatar requires a master video")
    if voice is None and audio is None:
        raise HTTPException(status_code=422, detail="Select a voice profile or provide an audio asset")

    script = json.loads(course.script_json or "[]")
    plan = plan_for_tenant(db, principal.tenant_id)
    server_estimate = estimate_script_seconds(script, fallback=saas_settings.default_render_estimate_seconds)
    reserved_seconds = max(server_estimate, int(body.estimated_seconds))
    effective_priority = int(plan.priority)

    payload = {
        "job_type": "course_render",
        "course_id": course.id,
        "ppt_asset_id": ppt.id,
        "avatar_id": avatar.id,
        "master_video_asset_id": avatar.master_video_asset_id,
        "voice_profile_id": voice.id if voice else None,
        "audio_asset_id": audio.id if audio else None,
        "script": script,
        "course_settings": json.loads(course.settings_json or "{}"),
        "priority": effective_priority,
    }
    queued = RenderJob(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        engine=body.engine,
        payload=payload,
    )
    record = RenderJobRecord(
        id=queued.id,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        course_id=course.id,
        engine=body.engine,
        status="queued",
        progress=0,
        stage="queued",
        payload_json=json.dumps(payload, ensure_ascii=False),
        estimated_seconds=reserved_seconds,
    )
    db.add(record)
    reserve_render_seconds(
        db,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        job_id=queued.id,
        seconds=reserved_seconds,
    )
    course.status = "queued"
    audit(
        db,
        action="render.enqueue",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="job",
        target_id=queued.id,
        details={
            "course_id": course.id,
            "engine": body.engine,
            "reserved_seconds": reserved_seconds,
            "plan_priority": effective_priority,
        },
    )
    db.commit()
    try:
        job_queue.enqueue(queued)
    except Exception as exc:
        record.status = "failed"
        record.stage = "queue_failed"
        record.error = str(exc)
        course.status = "draft"
        refund_render_seconds(
            db,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            job_id=queued.id,
            seconds=reserved_seconds,
        )
        db.commit()
        raise HTTPException(status_code=503, detail="Render queue unavailable") from exc
    return _job_dict(record)


@job_router.get("")
def list_jobs(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    items = db.scalars(
        select(RenderJobRecord)
        .where(RenderJobRecord.tenant_id == principal.tenant_id)
        .order_by(RenderJobRecord.created_at.desc())
        .limit(200)
    ).all()
    return [_job_dict(item) for item in items]


@job_router.get("/{job_id}")
def get_job(
    job_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = db.scalar(
        select(RenderJobRecord).where(
            RenderJobRecord.id == job_id,
            RenderJobRecord.tenant_id == principal.tenant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(item)


@job_router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = db.scalar(
        select(RenderJobRecord).where(
            RenderJobRecord.id == job_id,
            RenderJobRecord.tenant_id == principal.tenant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if item.user_id != principal.user_id and principal.role not in {"owner", "admin"} and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="You cannot cancel this job")
    if item.status != "queued":
        raise HTTPException(status_code=409, detail="Only queued jobs can be canceled")

    item.status = "canceled"
    item.stage = "canceled"
    item.completed_at = utcnow()
    refund_render_seconds(
        db,
        tenant_id=principal.tenant_id,
        user_id=item.user_id,
        job_id=item.id,
        seconds=item.estimated_seconds,
    )
    if item.course_id:
        course = db.get(Course, item.course_id)
        if course and course.tenant_id == principal.tenant_id:
            course.status = "draft"
    audit(db, action="render.cancel", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="job", target_id=item.id)
    db.commit()
    # Queue cancellation is best-effort; worker always re-checks DB state before rendering.
    try:
        job_queue.cancel(item.id)
    except Exception:
        pass
    return _job_dict(item)


@dashboard_router.get("")
def dashboard(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course_count = db.scalar(select(func.count()).select_from(Course).where(Course.tenant_id == principal.tenant_id)) or 0
    avatar_count = db.scalar(select(func.count()).select_from(Avatar).where(Avatar.tenant_id == principal.tenant_id)) or 0
    asset_count = db.scalar(select(func.count()).select_from(Asset).where(Asset.tenant_id == principal.tenant_id)) or 0
    running = db.scalar(
        select(func.count()).select_from(RenderJobRecord).where(
            RenderJobRecord.tenant_id == principal.tenant_id,
            RenderJobRecord.status.in_(["queued", "running"]),
        )
    ) or 0
    completed = db.scalar(
        select(func.count()).select_from(RenderJobRecord).where(
            RenderJobRecord.tenant_id == principal.tenant_id,
            RenderJobRecord.status == "succeeded",
        )
    ) or 0
    return {
        "courses": int(course_count),
        "avatars": int(avatar_count),
        "assets": int(asset_count),
        "active_jobs": int(running),
        "completed_jobs": int(completed),
    }
