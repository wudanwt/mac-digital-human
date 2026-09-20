"""API-only execution of portrait matting and speech previews on remote Macs."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .auxiliary_task_models import AuxiliaryTaskLease
from .avatar_matting_models import AvatarMattingJob
from .database import get_db
from .distributed_render_models import WorkerNode
from .distributed_worker_api import _materialized_object, _stream_path, _transfer_urls, get_worker_node
from .models import Asset, Avatar, Course, VoiceProfile
from .services import audit, enforce_storage_limit
from .settings import saas_settings
from .speech_preview_models import SpeechPreviewJob
from .speech_preview_service import synthesis_fingerprint
from .storage import object_store

router = APIRouter(prefix="/internal/render/aux", tags=["distributed-worker-internal"])
log = logging.getLogger("digital-human.saas.auxiliary-worker-api")
_SPECS = {
    "speech_preview": {"audio": (".wav", "audio/wav", "audio_preview")},
    "avatar_matting": {
        "alpha": (".mp4", "video/mp4", "avatar_alpha"),
        "poster": (".png", "image/png", "avatar_cutout"),
        "white": (".mp4", "video/mp4", "avatar_white"),
    },
}
_MAX_ARTIFACT_BYTES = 2**31 - 1  # Asset.size_bytes is a signed SQL INTEGER.


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _release_node(node: WorkerNode | None, lease: AuxiliaryTaskLease) -> None:
    if node is None:
        return
    node.slots_busy = max(0, node.slots_busy - 1)
    if node.current_task_id == lease.id:
        node.current_task_id = None
    if node.status not in {"revoked", "incompatible", "disk_low"}:
        node.status = "busy" if node.slots_busy else ("online" if node.accepting_tasks else "draining")


def _discard_artifacts(artifacts: dict[str, Any]) -> None:
    for artifact in artifacts.values():
        try:
            object_store.delete(artifact["object_key"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Unable to remove abandoned auxiliary artifact: %s", exc)


def reap_expired_auxiliary_leases(db: Session) -> int:
    leases = db.scalars(
        select(AuxiliaryTaskLease)
        .where(AuxiliaryTaskLease.expires_at <= _now())
        .with_for_update(skip_locked=True)
    ).all()
    for lease in leases:
        job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
        if job is not None and job.status == "running":
            job.status = "queued"
            job.progress = 0
            job.stage = "recovered"
            job.started_at = None
            job.updated_at = _now()
        _discard_artifacts(json.loads(lease.artifacts_json or "{}"))
        _release_node(db.get(WorkerNode, lease.node_id), lease)
        db.delete(lease)
    return len(leases)


def _verify(db: Session, node: WorkerNode, lease_id: str, token: str | None, *, lock: bool = False) -> AuxiliaryTaskLease:
    lease = db.scalar(
        select(AuxiliaryTaskLease).where(AuxiliaryTaskLease.id == lease_id).with_for_update()
    ) if lock else db.get(AuxiliaryTaskLease, lease_id)
    if lease is None or lease.node_id != node.id or not token or not hmac.compare_digest(
        lease.token_hash, hashlib.sha256(token.encode()).hexdigest()
    ):
        raise HTTPException(status_code=409, detail="Auxiliary task lease is invalid")
    if _utc(lease.expires_at) <= _now():
        raise HTTPException(status_code=409, detail="Auxiliary task lease expired")
    job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
    if job is None or job.status != "running":
        raise HTTPException(status_code=409, detail="Auxiliary task is no longer active")
    return lease


def _asset_descriptor(asset: Asset, lease_id: str) -> dict[str, Any]:
    proxy = f"{saas_settings.api_prefix}/internal/render/aux/{lease_id}/assets/{asset.id}"
    return {
        "id": asset.id,
        "name": asset.name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        **_transfer_urls(object_key=asset.object_key, proxy_url=proxy),
    }


def _has_available_preferred_worker(
    db: Session,
    required_capability: str,
    current_node_id: str,
) -> bool:
    cutoff = _now() - timedelta(seconds=max(15, saas_settings.distributed_reaper_seconds))
    nodes = db.scalars(
        select(WorkerNode)
        .where(
            WorkerNode.id != current_node_id,
            WorkerNode.status.in_(["online", "busy"]),
            WorkerNode.accepting_tasks.is_(True),
            WorkerNode.slots_busy < WorkerNode.slots_total,
            WorkerNode.last_seen_at >= cutoff,
        )
    ).all()
    for n in nodes:
        caps = set(json.loads(n.capabilities_json or "[]"))
        if "aux-routing:preferred" in caps and required_capability in caps:
            return True
    return False


@router.post("/claim")
def claim_auxiliary_task(
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not saas_settings.distributed_render_enabled:
        return {"task": None}
    reap_expired_auxiliary_leases(db)
    if node.status not in {"online", "busy"} or not node.accepting_tasks or node.slots_busy >= node.slots_total:
        db.commit()
        return {"task": None}
    capabilities = set(json.loads(node.capabilities_json or "[]"))
    is_preferred = "aux-routing:preferred" in capabilities
    for kind, model in (("speech_preview", SpeechPreviewJob), ("avatar_matting", AvatarMattingJob)):
        required = "speech-preview" if kind == "speech_preview" else "portrait-matting"
        if required not in capabilities:
            continue
        query = select(model).where(model.status == "queued")
        if not is_preferred and _has_available_preferred_worker(db, required, node.id):
            fallback_cutoff = _now() - timedelta(
                seconds=saas_settings.distributed_auxiliary_fallback_seconds
            )
            query = query.where(model.created_at <= fallback_cutoff)
        job = db.scalar(
            query.order_by(model.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            continue
        lease_id = uuid4().hex
        token = secrets.token_urlsafe(32)
        assets: list[Asset] = []
        if kind == "avatar_matting":
            avatar = db.get(Avatar, job.avatar_id)
            source = db.get(Asset, job.source_asset_id)
            if avatar is None or avatar.master_video_asset_id != job.source_asset_id or source is None or source.tenant_id != job.tenant_id:
                job.status, job.stage, job.error = "failed", "failed", "Master video is unavailable"
                job.completed_at = _now()
                db.commit()
                continue
            assets = [source]
            payload = {"model": job.model, "source_asset_id": source.id}
        else:
            course = db.get(Course, job.course_id)
            voice = db.get(VoiceProfile, job.voice_profile_id)
            reference = db.get(Asset, voice.reference_asset_id) if voice and voice.reference_asset_id else None
            if not course or not voice or not reference or course.tenant_id != job.tenant_id or voice.tenant_id != job.tenant_id or reference.tenant_id != job.tenant_id:
                job.status, job.stage, job.error = "failed", "failed", "Course or voice is unavailable"
                job.completed_at = _now()
                db.commit()
                continue
            settings = json.loads(course.settings_json or "{}")
            if synthesis_fingerprint(text=job.text, scope=job.scope, voice=voice, course_settings=settings) != job.text_hash:
                job.status, job.stage, job.error = "canceled", "superseded", "Voice or course settings changed"
                job.completed_at = _now()
                db.commit()
                continue
            assets = [reference]
            payload = {
                "text": job.text,
                "reference_asset_id": reference.id,
                "voice": {"id": voice.id, "provider": voice.provider, "transcript": voice.transcript, "settings": json.loads(voice.settings_json or "{}")},
                "course_settings": settings,
            }
        lease = AuxiliaryTaskLease(
            id=lease_id,
            kind=kind,
            job_id=job.id,
            node_id=node.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=_now() + timedelta(seconds=saas_settings.distributed_lease_seconds),
            artifacts_json="{}",
        )
        db.add(lease)
        job.status, job.stage, job.error = "running", "starting", None
        job.progress = 1
        job.started_at = job.updated_at = _now()
        node.slots_busy += 1
        node.status = "busy"
        node.current_task_id = lease_id
        log.info(
            "Auxiliary task claimed kind=%s job_id=%s node_id=%s node_name=%s preferred=%s",
            kind, job.id, node.id, node.name, is_preferred,
        )
        descriptor = {
            "id": lease_id,
            "kind": kind,
            "job_id": job.id,
            "lease_token": token,
            "assets": [_asset_descriptor(asset, lease_id) for asset in assets],
            "payload": payload,
        }
        db.commit()
        return {"task": descriptor}
    db.commit()
    return {"task": None}


class LeaseBody(BaseModel):
    lease_token: str = Field(min_length=16, max_length=512)


class ProgressBody(LeaseBody):
    progress: int = Field(ge=0, le=99)
    stage: str = Field(min_length=1, max_length=80)


class CompleteBody(LeaseBody):
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailBody(LeaseBody):
    error: str = Field(min_length=1, max_length=8000)


@router.post("/{lease_id}/renew")
def renew_auxiliary_task(lease_id: str, body: LeaseBody, node: Annotated[WorkerNode, Depends(get_worker_node)], db: Annotated[Session, Depends(get_db)]):
    lease = _verify(db, node, lease_id, body.lease_token, lock=True)
    lease.expires_at = _now() + timedelta(seconds=saas_settings.distributed_lease_seconds)
    db.commit()
    return {"lease_expires_at": lease.expires_at.isoformat()}


@router.post("/{lease_id}/progress")
def progress_auxiliary_task(lease_id: str, body: ProgressBody, node: Annotated[WorkerNode, Depends(get_worker_node)], db: Annotated[Session, Depends(get_db)]):
    lease = _verify(db, node, lease_id, body.lease_token, lock=True)
    job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
    job.progress = max(job.progress, body.progress)
    job.stage = body.stage
    job.updated_at = _now()
    db.commit()
    return {"ok": True}


@router.get("/{lease_id}/assets/{asset_id}")
def download_auxiliary_asset(
    lease_id: str,
    asset_id: str,
    background: BackgroundTasks,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    lease = _verify(db, node, lease_id, x_lease_token)
    job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
    asset_id_allowed = job.source_asset_id if lease.kind == "avatar_matting" else db.get(VoiceProfile, job.voice_profile_id).reference_asset_id
    if asset_id != asset_id_allowed:
        raise HTTPException(status_code=403, detail="Asset is not assigned to this task")
    asset = db.get(Asset, asset_id)
    if asset is None or asset.tenant_id != job.tenant_id or asset.status != "ready":
        raise HTTPException(status_code=404, detail="Task asset not found")
    path, temporary = _materialized_object(asset.object_key, Path(asset.name).suffix)
    if temporary:
        background.add_task(path.unlink, missing_ok=True)
    return _stream_path(path, range_header=range_header, content_type=asset.content_type, background=background)


@router.put("/{lease_id}/artifacts/{kind}")
async def upload_auxiliary_artifact(
    lease_id: str,
    kind: str,
    request: Request,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
    x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
):
    lease = _verify(db, node, lease_id, x_lease_token)
    if kind not in _SPECS[lease.kind]:
        raise HTTPException(status_code=422, detail="Unsupported artifact kind")
    if not x_content_sha256 or len(x_content_sha256) != 64:
        raise HTTPException(status_code=422, detail="Artifact SHA-256 is required")
    suffix, content_type, _ = _SPECS[lease.kind][kind]
    fd, name = tempfile.mkstemp(prefix="aux-upload-", suffix=suffix)
    path = Path(name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as target:
            async for chunk in request.stream():
                size += len(chunk)
                if size > _MAX_ARTIFACT_BYTES:
                    raise HTTPException(status_code=413, detail="Artifact is too large")
                digest.update(chunk)
                target.write(chunk)
        if not size or not hmac.compare_digest(digest.hexdigest(), x_content_sha256.lower()):
            raise HTTPException(status_code=422, detail="Artifact size or hash mismatch")
        lease = _verify(db, node, lease_id, x_lease_token, lock=True)
        artifacts = json.loads(lease.artifacts_json or "{}")
        previous = artifacts.get(kind)
        if previous and previous["sha256"] == digest.hexdigest():
            return {"ok": True, "size_bytes": size}
        job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
        key = f"{job.tenant_id}/remote-aux/{lease.id}/{kind}{suffix}"
        uri = object_store.put_file(path, key)
        artifacts[kind] = {"object_key": key, "uri": uri, "sha256": digest.hexdigest(), "size_bytes": size, "content_type": content_type}
        lease.artifacts_json = json.dumps(artifacts)
        db.commit()
        return {"ok": True, "size_bytes": size}
    finally:
        path.unlink(missing_ok=True)


@router.post("/{lease_id}/complete")
def complete_auxiliary_task(lease_id: str, body: CompleteBody, node: Annotated[WorkerNode, Depends(get_worker_node)], db: Annotated[Session, Depends(get_db)]):
    lease = _verify(db, node, lease_id, body.lease_token, lock=True)
    job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
    artifacts = json.loads(lease.artifacts_json or "{}")
    if set(artifacts) != set(_SPECS[lease.kind]):
        raise HTTPException(status_code=409, detail="Task artifacts are incomplete")
    for item in artifacts.values():
        if object_store.object_size(item["object_key"]) != item["size_bytes"]:
            raise HTTPException(status_code=409, detail="Task artifact is unavailable or incomplete")
    if lease.kind == "avatar_matting":
        avatar = db.get(Avatar, job.avatar_id)
        valid = avatar is not None and avatar.master_video_asset_id == job.source_asset_id
    else:
        course = db.get(Course, job.course_id)
        voice = db.get(VoiceProfile, job.voice_profile_id)
        valid = bool(course and voice and synthesis_fingerprint(text=job.text, scope=job.scope, voice=voice, course_settings=json.loads(course.settings_json or "{}")) == job.text_hash)
    if not valid:
        job.status, job.stage, job.error = "canceled", "superseded", "Task inputs changed"
        job.completed_at = job.updated_at = _now()
        _discard_artifacts(artifacts)
        _release_node(node, lease)
        db.delete(lease)
        db.commit()
        return {"status": "canceled"}
    enforce_storage_limit(db, job.tenant_id, incoming_bytes=sum(item["size_bytes"] for item in artifacts.values()))
    created: dict[str, Asset] = {}
    for kind, item in artifacts.items():
        suffix, content_type, asset_kind = _SPECS[lease.kind][kind]
        asset = Asset(
            tenant_id=job.tenant_id,
            user_id=job.user_id,
            kind=asset_kind,
            name=f"{job.id}-{kind}{suffix}",
            object_key=item["object_key"],
            uri=item["uri"],
            content_type=content_type,
            size_bytes=item["size_bytes"],
            sha256=item["sha256"],
            status="ready",
        )
        db.add(asset)
        db.flush()
        created[kind] = asset
    if lease.kind == "avatar_matting":
        job.alpha_asset_id = created["alpha"].id
        job.poster_asset_id = created["poster"].id
        job.white_preview_asset_id = created["white"].id
        job.metadata_json = json.dumps(body.metadata, ensure_ascii=False)
        target_type, target_id, action = "avatar", job.avatar_id, "avatar.matting.completed"
    else:
        job.audio_asset_id = created["audio"].id
        target_type, target_id, action = "course", job.course_id, "course.speech_preview.completed"
    job.status, job.stage, job.error = "succeeded", "completed", None
    job.progress = 100
    job.completed_at = job.updated_at = _now()
    audit(
        db,
        action=action,
        tenant_id=job.tenant_id,
        user_id=job.user_id,
        target_type=target_type,
        target_id=target_id,
        details={
            "job_id": job.id,
            "remote_worker_id": node.id,
            "remote_worker_name": node.name,
        },
    )
    _release_node(node, lease)
    db.delete(lease)
    db.commit()
    return {"status": "succeeded"}


@router.post("/{lease_id}/fail")
def fail_auxiliary_task(lease_id: str, body: FailBody, node: Annotated[WorkerNode, Depends(get_worker_node)], db: Annotated[Session, Depends(get_db)]):
    lease = _verify(db, node, lease_id, body.lease_token, lock=True)
    job = db.get(AvatarMattingJob if lease.kind == "avatar_matting" else SpeechPreviewJob, lease.job_id)
    job.status, job.stage, job.error = "failed", "failed", body.error
    job.progress = 100
    job.completed_at = job.updated_at = _now()
    _discard_artifacts(json.loads(lease.artifacts_json or "{}"))
    _release_node(node, lease)
    db.delete(lease)
    db.commit()
    return {"status": "failed"}
