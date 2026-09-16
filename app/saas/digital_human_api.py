from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Asset, Avatar, ConsentRecord, Course, VoiceProfile
from .security import Principal, get_principal, require_admin
from .services import audit, enforce_avatar_limit, enforce_storage_limit
from .settings import saas_settings
from .storage import object_store


router = APIRouter(prefix="/digital-humans", tags=["digital-humans"])

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".webm", ".mp4"}


def _asset_dict(asset: Asset | None) -> dict | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "download_url": f"{saas_settings.api_prefix}/assets/{asset.id}/download",
    }


def _voice_dict(voice: VoiceProfile | None, ref_asset: Asset | None = None) -> dict | None:
    if voice is None:
        return None
    return {
        "id": voice.id,
        "name": voice.name,
        "provider": voice.provider,
        "reference_asset_id": voice.reference_asset_id,
        "reference_asset": _asset_dict(ref_asset),
        "transcript": voice.transcript,
        "settings": json.loads(voice.settings_json or "{}"),
    }


def _digital_human_dict(db: Session, avatar: Avatar) -> dict:
    image = db.get(Asset, avatar.image_asset_id) if avatar.image_asset_id else None
    master = db.get(Asset, avatar.master_video_asset_id) if avatar.master_video_asset_id else None
    voice = db.get(VoiceProfile, avatar.voice_profile_id) if avatar.voice_profile_id else None
    ref = db.get(Asset, voice.reference_asset_id) if voice and voice.reference_asset_id else None
    return {
        "id": avatar.id,
        "name": avatar.name,
        "prompt": avatar.prompt,
        "status": avatar.status,
        "image_asset_id": avatar.image_asset_id,
        "master_video_asset_id": avatar.master_video_asset_id,
        "voice_profile_id": avatar.voice_profile_id,
        "image": _asset_dict(image),
        "master_video": _asset_dict(master),
        "voice": _voice_dict(voice, ref),
        "readiness": {
            "portrait_ready": bool(image or master),
            "master_video_ready": bool(master),
            "voice_ready": bool(voice and ref and voice.transcript.strip()),
            "musetalk_ready": bool(master and voice and ref and voice.transcript.strip()),
        },
        "created_at": avatar.created_at.isoformat(),
        "updated_at": avatar.updated_at.isoformat(),
    }


def _existing_asset(db: Session, tenant_id: str, asset_id: str | None, kind: str) -> Asset | None:
    if not asset_id:
        return None
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))
    if asset is None:
        raise HTTPException(status_code=404, detail=f"{kind} asset not found")
    if asset.kind != kind:
        raise HTTPException(status_code=422, detail=f"Expected {kind} asset, got {asset.kind}")
    return asset


def _existing_voice(db: Session, tenant_id: str, voice_id: str | None) -> VoiceProfile | None:
    if not voice_id:
        return None
    voice = db.scalar(select(VoiceProfile).where(VoiceProfile.id == voice_id, VoiceProfile.tenant_id == tenant_id))
    if voice is None:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    if not voice.reference_asset_id or not voice.transcript.strip():
        raise HTTPException(status_code=422, detail="Selected voice is incomplete and cannot be used for cloning")
    ref = _existing_asset(db, tenant_id, voice.reference_asset_id, "audio")
    if ref is None:
        raise HTTPException(status_code=422, detail="Selected voice reference audio is missing")
    return voice


def _extension(upload: UploadFile, allowed: set[str], label: str) -> str:
    filename = Path(upload.filename or f"{label}.bin").name
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported {label} format: {ext or 'unknown'}")
    return ext


def _store_upload(
    db: Session,
    principal: Principal,
    upload: UploadFile,
    *,
    kind: str,
    allowed: set[str],
    label: str,
) -> tuple[Asset, str]:
    ext = _extension(upload, allowed, label)
    original = Path(upload.filename or f"{label}{ext}").name
    max_bytes = saas_settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    fd, temp_name = tempfile.mkstemp(prefix=f"digital-human-{kind}-", suffix=ext)
    os.close(fd)
    temp_path = Path(temp_name)
    object_key = f"{principal.tenant_id}/{kind}/{uuid4().hex}{ext}"
    try:
        with temp_path.open("wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds {saas_settings.max_upload_mb} MB limit")
                digest.update(chunk)
                out.write(chunk)
        if size <= 0:
            raise HTTPException(status_code=422, detail=f"{label} file is empty")
        enforce_storage_limit(db, principal.tenant_id, incoming_bytes=size)
        uri = object_store.put_file(temp_path, object_key)
        asset = Asset(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            kind=kind,
            name=original,
            object_key=object_key,
            uri=uri,
            content_type=upload.content_type or "application/octet-stream",
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
        db.add(asset)
        db.flush()
        audit(
            db,
            action="asset.upload",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type="asset",
            target_id=asset.id,
            details={"kind": kind, "size": size, "source": "digital_human_wizard"},
        )
        return asset, object_key
    finally:
        temp_path.unlink(missing_ok=True)
        upload.file.close()


def _record_consent(
    db: Session,
    principal: Principal,
    *,
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
        details={"consent_type": consent_type},
    )


@router.get("")
def list_digital_humans(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    items = db.scalars(
        select(Avatar).where(Avatar.tenant_id == principal.tenant_id).order_by(Avatar.created_at.desc())
    ).all()
    return [_digital_human_dict(db, item) for item in items]


@router.get("/{avatar_id}")
def get_digital_human(
    avatar_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == principal.tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    return _digital_human_dict(db, item)


@router.post("", status_code=201)
def create_digital_human(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    name: str = Form(...),
    prompt: str = Form(""),
    image_file: UploadFile | None = File(None),
    master_video_file: UploadFile | None = File(None),
    existing_image_asset_id: str | None = Form(None),
    existing_master_video_asset_id: str | None = Form(None),
    existing_voice_profile_id: str | None = Form(None),
    voice_name: str = Form(""),
    voice_transcript: str = Form(""),
    voice_file: UploadFile | None = File(None),
    portrait_consent: bool = Form(False),
    voice_consent: bool = Form(False),
) -> dict:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Digital human name is required")
    if not portrait_consent:
        raise HTTPException(status_code=422, detail="Portrait/video authorization must be confirmed")
    if bool(image_file) and bool(existing_image_asset_id):
        raise HTTPException(status_code=422, detail="Choose either a new image upload or an existing image")
    if bool(master_video_file) and bool(existing_master_video_asset_id):
        raise HTTPException(status_code=422, detail="Choose either a new master video or an existing master video")
    if bool(voice_file) and bool(existing_voice_profile_id):
        raise HTTPException(status_code=422, detail="Choose either a new cloned voice or an existing voice")

    enforce_avatar_limit(db, principal.tenant_id)
    created_keys: list[str] = []
    try:
        image_asset = _existing_asset(db, principal.tenant_id, existing_image_asset_id, "image")
        master_asset = _existing_asset(db, principal.tenant_id, existing_master_video_asset_id, "video")
        voice = _existing_voice(db, principal.tenant_id, existing_voice_profile_id)

        if image_file is not None:
            image_asset, key = _store_upload(
                db, principal, image_file, kind="image", allowed=_IMAGE_EXTENSIONS, label="portrait image"
            )
            created_keys.append(key)
        if master_video_file is not None:
            master_asset, key = _store_upload(
                db, principal, master_video_file, kind="video", allowed=_VIDEO_EXTENSIONS, label="master video"
            )
            created_keys.append(key)

        if image_asset is None and master_asset is None:
            raise HTTPException(status_code=422, detail="Upload a portrait image or master video")
        if master_asset is None:
            raise HTTPException(status_code=422, detail="A master video is required for the current MuseTalk digital-human engine")

        if voice_file is not None:
            if not voice_consent:
                raise HTTPException(status_code=422, detail="Voice-cloning authorization must be confirmed")
            if not voice_transcript.strip():
                raise HTTPException(status_code=422, detail="Reference recording transcript is required")
            audio_asset, key = _store_upload(
                db, principal, voice_file, kind="audio", allowed=_AUDIO_EXTENSIONS, label="voice recording"
            )
            created_keys.append(key)
            voice = VoiceProfile(
                tenant_id=principal.tenant_id,
                name=voice_name.strip() or f"{clean_name}的声音",
                provider="cosyvoice",
                reference_asset_id=audio_asset.id,
                transcript=voice_transcript.strip(),
                settings_json="{}",
            )
            db.add(voice)
            db.flush()
            _record_consent(
                db,
                principal,
                subject_type="voice",
                subject_id=voice.id,
                consent_type="voice_clone_authorization",
                statement="I confirm authorization to use this recording for synthetic voice generation.",
            )
            audit(
                db,
                action="voice.create",
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                target_type="voice",
                target_id=voice.id,
                details={"source": "digital_human_wizard"},
            )

        if voice is None:
            raise HTTPException(status_code=422, detail="Configure a cloned voice or select an existing voice")

        avatar = Avatar(
            tenant_id=principal.tenant_id,
            name=clean_name,
            image_asset_id=image_asset.id if image_asset else None,
            master_video_asset_id=master_asset.id,
            voice_profile_id=voice.id,
            prompt=prompt.strip(),
            status="ready",
        )
        db.add(avatar)
        db.flush()
        _record_consent(
            db,
            principal,
            subject_type="avatar",
            subject_id=avatar.id,
            consent_type="portrait_synthesis_authorization",
            statement="I confirm authorization to use this person's image/video for digital-human synthesis.",
        )
        audit(
            db,
            action="digital_human.create",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type="avatar",
            target_id=avatar.id,
            details={"voice_profile_id": voice.id, "source": "digital_human_wizard"},
        )
        db.commit()
        return _digital_human_dict(db, avatar)
    except Exception:
        db.rollback()
        for key in created_keys:
            try:
                object_store.delete(key)
            except Exception:
                pass
        raise


@router.patch("/{avatar_id}")
def update_digital_human(
    avatar_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    name: str | None = Form(None),
    prompt: str | None = Form(None),
    image_file: UploadFile | None = File(None),
    master_video_file: UploadFile | None = File(None),
    voice_file: UploadFile | None = File(None),
    existing_voice_profile_id: str | None = Form(None),
    voice_name: str = Form(""),
    voice_transcript: str = Form(""),
    portrait_consent: bool = Form(False),
    voice_consent: bool = Form(False),
) -> dict:
    avatar = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == principal.tenant_id))
    if avatar is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    created_keys: list[str] = []
    try:
        if name is not None and name.strip():
            avatar.name = name.strip()
        if prompt is not None:
            avatar.prompt = prompt.strip()

        if image_file is not None or master_video_file is not None:
            if not portrait_consent:
                raise HTTPException(status_code=422, detail="Portrait/video authorization must be confirmed for replacement media")
            if image_file is not None:
                image, key = _store_upload(
                    db, principal, image_file, kind="image", allowed=_IMAGE_EXTENSIONS, label="portrait image"
                )
                created_keys.append(key)
                avatar.image_asset_id = image.id
            if master_video_file is not None:
                master, key = _store_upload(
                    db, principal, master_video_file, kind="video", allowed=_VIDEO_EXTENSIONS, label="master video"
                )
                created_keys.append(key)
                avatar.master_video_asset_id = master.id
            _record_consent(
                db,
                principal,
                subject_type="avatar",
                subject_id=avatar.id,
                consent_type="portrait_synthesis_authorization",
                statement="I confirm authorization for the replacement portrait/video media.",
            )

        if existing_voice_profile_id:
            avatar.voice_profile_id = _existing_voice(db, principal.tenant_id, existing_voice_profile_id).id
        elif voice_file is not None:
            if not voice_consent:
                raise HTTPException(status_code=422, detail="Voice-cloning authorization must be confirmed")
            if not voice_transcript.strip():
                raise HTTPException(status_code=422, detail="Reference recording transcript is required")
            audio, key = _store_upload(
                db, principal, voice_file, kind="audio", allowed=_AUDIO_EXTENSIONS, label="voice recording"
            )
            created_keys.append(key)
            voice = VoiceProfile(
                tenant_id=principal.tenant_id,
                name=voice_name.strip() or f"{avatar.name}的声音",
                provider="cosyvoice",
                reference_asset_id=audio.id,
                transcript=voice_transcript.strip(),
                settings_json="{}",
            )
            db.add(voice)
            db.flush()
            avatar.voice_profile_id = voice.id
            _record_consent(
                db,
                principal,
                subject_type="voice",
                subject_id=voice.id,
                consent_type="voice_clone_authorization",
                statement="I confirm authorization to use this replacement recording for synthetic voice generation.",
            )

        avatar.status = "ready" if avatar.master_video_asset_id and avatar.voice_profile_id else "incomplete"
        audit(
            db,
            action="digital_human.update",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type="avatar",
            target_id=avatar.id,
            details={"voice_profile_id": avatar.voice_profile_id},
        )
        db.commit()
        return _digital_human_dict(db, avatar)
    except Exception:
        db.rollback()
        for key in created_keys:
            try:
                object_store.delete(key)
            except Exception:
                pass
        raise


@router.delete("/{avatar_id}", status_code=204)
def delete_digital_human(
    avatar_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    avatar = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == principal.tenant_id))
    if avatar is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    if db.scalar(select(Course.id).where(Course.tenant_id == principal.tenant_id, Course.avatar_id == avatar.id).limit(1)):
        raise HTTPException(status_code=409, detail="Digital human is referenced by a course")
    db.delete(avatar)
    audit(
        db,
        action="digital_human.delete",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="avatar",
        target_id=avatar.id,
    )
    db.commit()
