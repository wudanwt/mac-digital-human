from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.background import BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from .database import get_db
from .distributed_render_models import RenderArtifact, RenderAttempt, RenderSubtask, WorkerEnrollment, WorkerNode
from .distributed_scheduler import (
    LeaseConflict,
    SchedulerError,
    as_utc,
    claim_page_task,
    complete_page_task,
    fail_page_task,
    hash_secret,
    renew_lease,
    report_progress,
)
from .media_cues import media_cue_asset_ids
from .models import Asset, RenderJobRecord
from .render_snapshot_models import RenderTaskSnapshot
from .security import Principal, require_admin
from .settings import saas_settings
from .storage import object_store

admin_router = APIRouter(prefix="/distributed/workers", tags=["distributed-workers"])
internal_router = APIRouter(prefix="/internal/render", tags=["distributed-worker-internal"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_UPLOAD_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_ALLOWED_ARTIFACT_KINDS = {"page_video", "page_audio"}

log = logging.getLogger("digital-human.saas.distributed-worker-api")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def _worker_token(node_id: str) -> str:
    return f"wrk_{node_id}_{secrets.token_urlsafe(32)}"


def _enrollment_code(enrollment_id: str) -> str:
    return f"enr_{enrollment_id}_{secrets.token_urlsafe(24)}"


def _serialize_node(node: WorkerNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "name": node.name,
        "status": node.status,
        "accepting_tasks": node.accepting_tasks,
        "slots_total": node.slots_total,
        "slots_busy": node.slots_busy,
        "host": node.host,
        "platform": node.platform,
        "machine": node.machine,
        "capabilities": _json(node.capabilities_json, []),
        "versions": _json(node.versions_json, {}),
        "code_version": node.code_version,
        "model_version": node.model_version,
        "render_contract_version": node.render_contract_version,
        "current_task_id": node.current_task_id,
        "last_error": node.last_error,
        "disk_free_bytes": node.disk_free_bytes,
        "memory_available_mb": node.memory_available_mb,
        "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


class WorkerProvisionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slots_total: int = Field(default=1, ge=1, le=4)


class WorkerEnrollmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slots_total: int = Field(default=1, ge=1, le=4)


class WorkerEnrollRequest(BaseModel):
    enrollment_code: str = Field(min_length=16, max_length=512)
    name: str | None = Field(default=None, max_length=120)
    host: str = Field(default="", max_length=255)
    platform: str = Field(default="", max_length=255)
    machine: str = Field(default="", max_length=80)


class WorkerAcceptingRequest(BaseModel):
    accepting_tasks: bool


class WorkerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(default="", max_length=255)
    platform: str = Field(default="", max_length=255)
    machine: str = Field(default="", max_length=80)
    slots_total: int = Field(default=1, ge=1, le=4)
    capabilities: list[str] = Field(default_factory=list)
    versions: dict[str, str] = Field(default_factory=dict)
    code_version: str = Field(default="", max_length=120)
    model_version: str = Field(default="", max_length=120)
    render_contract_version: str = Field(default="", max_length=120)


class WorkerHeartbeatRequest(BaseModel):
    current_task_id: str | None = Field(default=None, max_length=32)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    memory_available_mb: int | None = Field(default=None, ge=0)
    last_error: str | None = Field(default=None, max_length=4000)
    versions: dict[str, str] | None = None


class LeaseRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=32)
    lease_token: str = Field(min_length=16, max_length=512)


class ProgressRequest(LeaseRequest):
    progress: int = Field(ge=0, le=99)
    stage: str = Field(min_length=1, max_length=80)
    metrics: dict[str, Any] = Field(default_factory=dict)


class CompleteRequest(LeaseRequest):
    metrics: dict[str, Any] = Field(default_factory=dict)
    media: dict[str, Any] = Field(default_factory=dict)


class FailRequest(LeaseRequest):
    error: str = Field(min_length=1, max_length=8000)
    retryable: bool = True
    metrics: dict[str, Any] = Field(default_factory=dict)


class DirectUploadRequest(BaseModel):
    size_bytes: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class DirectUploadCommitRequest(DirectUploadRequest):
    object_key: str = Field(min_length=1, max_length=900)


@admin_router.post("", status_code=201)
def provision_worker(
    body: WorkerProvisionRequest,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node_id = uuid4().hex
    token = _worker_token(node_id)
    node = WorkerNode(
        id=node_id,
        name=body.name.strip(),
        credential_hash=hash_secret(token),
        status="offline",
        accepting_tasks=True,
        slots_total=body.slots_total,
        slots_busy=0,
        render_contract_version="",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return {"worker": _serialize_node(node), "token": token}


@admin_router.post("/enrollments", status_code=201)
def create_worker_enrollment(
    body: WorkerEnrollmentRequest,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node_id = uuid4().hex
    enrollment_id = uuid4().hex
    code = _enrollment_code(enrollment_id)
    now = _now()
    expires_at = now + timedelta(
        minutes=max(5, min(1440, saas_settings.distributed_enrollment_minutes))
    )
    # WorkerNode keeps its existing non-null/unique credential invariant. This
    # random pending value is never returned to a client and is atomically
    # replaced by a real Worker credential when enrollment succeeds.
    node = WorkerNode(
        id=node_id,
        name=body.name.strip(),
        credential_hash=hash_secret(f"pending:{node_id}:{secrets.token_urlsafe(32)}"),
        status="pending",
        accepting_tasks=False,
        slots_total=body.slots_total,
        slots_busy=0,
        render_contract_version="",
    )
    enrollment = WorkerEnrollment(
        id=enrollment_id,
        node_id=node_id,
        token_hash=hash_secret(code),
        expires_at=expires_at,
        used_at=None,
    )
    db.add(node)
    db.flush()
    db.add(enrollment)
    db.commit()
    db.refresh(node)
    return {
        "worker": _serialize_node(node),
        "enrollment_code": code,
        "expires_at": expires_at.isoformat(),
    }


@internal_router.post("/enroll")
def enroll_worker(
    body: WorkerEnrollRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    digest = hash_secret(body.enrollment_code.strip())
    enrollment = db.scalar(
        select(WorkerEnrollment)
        .where(WorkerEnrollment.token_hash == digest)
        .with_for_update()
    )
    now = _now()
    if (
        enrollment is None
        or enrollment.used_at is not None
        or as_utc(enrollment.expires_at) <= now
    ):
        db.rollback()
        raise HTTPException(status_code=401, detail="Invalid or expired enrollment code")

    node = db.get(WorkerNode, enrollment.node_id)
    if node is None or node.status == "revoked":
        db.rollback()
        raise HTTPException(status_code=409, detail="Worker enrollment is no longer available")

    token = _worker_token(node.id)
    node.credential_hash = hash_secret(token)
    node.accepting_tasks = True
    node.status = "offline"
    if body.name and body.name.strip():
        node.name = body.name.strip()
    node.host = body.host.strip()
    node.platform = body.platform.strip()
    node.machine = body.machine.strip()
    node.last_error = None
    enrollment.used_at = now
    db.commit()
    db.refresh(node)
    return {
        "worker": _serialize_node(node),
        "token": token,
    }


@admin_router.get("")
def list_distributed_workers(
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    del principal
    items = db.scalars(select(WorkerNode).order_by(WorkerNode.created_at.asc())).all()
    return [_serialize_node(item) for item in items]


@admin_router.patch("/{node_id}/accepting")
def set_worker_accepting(
    node_id: str,
    body: WorkerAcceptingRequest,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node = db.get(WorkerNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Worker node not found")
    if node.status == "revoked":
        raise HTTPException(status_code=409, detail="Worker credential is revoked")
    node.accepting_tasks = body.accepting_tasks
    if not body.accepting_tasks:
        node.status = "draining" if node.slots_busy else "offline"
    elif node.last_seen_at:
        node.status = "busy" if node.slots_busy else "online"
    db.commit()
    return _serialize_node(node)


@admin_router.post("/{node_id}/revoke")
def revoke_worker(
    node_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node = db.get(WorkerNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Worker node not found")
    if node.slots_busy:
        raise HTTPException(status_code=409, detail="Drain the worker before revoking its credential")
    node.accepting_tasks = False
    node.status = "revoked"
    node.credential_hash = hash_secret(f"revoked:{node.id}:{secrets.token_urlsafe(32)}")
    node.current_task_id = None
    db.commit()
    return _serialize_node(node)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Worker authentication required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Worker bearer token required")
    return token.strip()


def get_worker_node(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> WorkerNode:
    token = _bearer_token(authorization)
    digest = hash_secret(token)
    node = db.scalar(select(WorkerNode).where(WorkerNode.credential_hash == digest))
    if node is None or node.status == "revoked":
        raise HTTPException(status_code=401, detail="Invalid or revoked worker credential")
    return node


def _compatibility_error(body: WorkerRegisterRequest) -> str | None:
    if body.render_contract_version != saas_settings.render_contract_version:
        return (
            f"render contract mismatch: {body.render_contract_version or 'missing'} "
            f"!= {saas_settings.render_contract_version}"
        )
    expected_code = saas_settings.distributed_expected_code_version.strip()
    if expected_code and body.code_version != expected_code:
        return f"code version mismatch: {body.code_version or 'missing'} != {expected_code}"
    expected_model = saas_settings.distributed_expected_model_version.strip()
    if expected_model:
        accepted_models = {item.strip() for item in expected_model.split(",") if item.strip()}
        if body.model_version not in accepted_models:
            expected_label = ",".join(sorted(accepted_models))
            return f"model version mismatch: {body.model_version or 'missing'} not in {expected_label}"
    if "musetalk" not in {item.strip().lower() for item in body.capabilities}:
        return "worker does not advertise musetalk capability"
    return None


@internal_router.post("/register")
def register_worker_runtime(
    body: WorkerRegisterRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    was_incompatible = node.status == "incompatible"
    error = _compatibility_error(body)
    node.name = body.name.strip()
    node.host = body.host.strip()
    node.platform = body.platform.strip()
    node.machine = body.machine.strip()
    node.slots_total = body.slots_total
    node.capabilities_json = json.dumps(body.capabilities, ensure_ascii=False, sort_keys=True)
    node.versions_json = json.dumps(body.versions, ensure_ascii=False, sort_keys=True)
    node.code_version = body.code_version.strip()
    node.model_version = body.model_version.strip()
    node.render_contract_version = body.render_contract_version.strip()
    node.last_seen_at = _now()
    node.last_error = error
    if error:
        node.accepting_tasks = False
        node.status = "incompatible"
    else:
        # An incompatibility automatically drains the node. If the same worker
        # later registers with a compatible runtime, restore automatic
        # acceptance unless an operator changed its state after that failure.
        if was_incompatible and not node.accepting_tasks:
            node.accepting_tasks = True
        node.status = "busy" if node.slots_busy else ("online" if node.accepting_tasks else "draining")
    db.commit()
    if error:
        raise HTTPException(status_code=409, detail=error)
    return {"worker": _serialize_node(node), "lease_seconds": saas_settings.distributed_lease_seconds}


@internal_router.post("/heartbeat")
def worker_heartbeat(
    body: WorkerHeartbeatRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    node.last_seen_at = _now()
    node.disk_free_bytes = body.disk_free_bytes
    node.memory_available_mb = body.memory_available_mb
    node.last_error = body.last_error
    if body.versions is not None:
        node.versions_json = json.dumps(body.versions, ensure_ascii=False, sort_keys=True)
    min_free = saas_settings.distributed_min_disk_free_gb * 1024**3
    disk_blocked = body.disk_free_bytes is not None and body.disk_free_bytes < min_free
    if disk_blocked:
        # Disk pressure is an automatic eligibility gate, not an operator drain.
        # Keep accepting_tasks unchanged so the same worker can recover
        # automatically once cleanup restores the configured free-space margin.
        node.status = "disk_low"
        node.last_error = node.last_error or f"disk free below {saas_settings.distributed_min_disk_free_gb} GB"
    elif node.status not in {"incompatible", "revoked"}:
        # Older workers may have been auto-drained by the previous disk-low
        # behavior. A node still marked disk_low was not explicitly drained, so
        # restore its automatic acceptance when free space is healthy again.
        if node.status == "disk_low" and not node.accepting_tasks:
            node.accepting_tasks = True
        node.status = "busy" if node.slots_busy else ("online" if node.accepting_tasks else "draining")
    db.commit()
    return {"worker": _serialize_node(node), "server_time": _now().isoformat()}


def _snapshot_payload(db: Session, parent_job_id: str) -> dict[str, Any]:
    row = db.get(RenderTaskSnapshot, parent_job_id)
    if row is None:
        raise HTTPException(status_code=409, detail="Immutable render snapshot is missing")
    payload = _json(row.snapshot_json, {})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=409, detail="Immutable render snapshot is invalid")
    return payload


def _page_snapshot(snapshot: dict[str, Any], slide_index: int) -> dict[str, Any]:
    for raw in snapshot.get("pages") or []:
        if isinstance(raw, dict) and int(raw.get("index") or 0) == slide_index:
            return dict(raw)
    return {}


def _allowed_asset_ids(db: Session, task: RenderSubtask) -> set[str]:
    snapshot = _snapshot_payload(db, task.parent_job_id)
    page = _page_snapshot(snapshot, task.slide_index)
    common = [
        (snapshot.get("avatar") or {}).get("master_video_asset_id"),
        (snapshot.get("voice") or {}).get("reference_asset_id") if snapshot.get("voice") else None,
        snapshot.get("alpha_asset_id"),
        snapshot.get("direct_audio_asset_id"),
    ]
    page_items = [
        page.get("explicit_audio_asset_id"),
        page.get("preview_audio_asset_id"),
        page.get("background_asset_id"),
    ]
    page_items.extend(sorted(media_cue_asset_ids(page.get("media_cues"))))
    payload = _json(task.payload_json, {})
    if isinstance(payload, dict):
        page_items.extend(
            payload.get(key)
            for key in ("audio_asset_id", "background_asset_id", "master_video_asset_id", "reference_audio_asset_id", "alpha_asset_id")
        )
        page_items.extend(sorted(media_cue_asset_ids(payload.get("media_cues"))))
        override = payload.get("override")
        if isinstance(override, dict):
            page_items.extend(sorted(media_cue_asset_ids(override.get("media_cues"))))
    return {str(value) for value in (*common, *page_items) if value}


def _allowed_prepared_artifact_ids(db: Session, task: RenderSubtask) -> set[str]:
    payload = _json(task.payload_json, {})
    ids: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.endswith("_artifact_id") and value:
                ids.add(str(value))
    return ids


def _verify_attempt(
    db: Session,
    *,
    task_id: str,
    node: WorkerNode,
    attempt_id: str,
    lease_token: str,
    allow_completed: bool = False,
) -> tuple[RenderSubtask, RenderAttempt]:
    task = db.get(RenderSubtask, task_id)
    attempt = db.get(RenderAttempt, attempt_id)
    if task is None or attempt is None:
        raise HTTPException(status_code=404, detail="Task attempt not found")
    if attempt.subtask_id != task.id or attempt.node_id != node.id:
        raise HTTPException(status_code=409, detail="Task attempt ownership mismatch")
    if not hmac.compare_digest(attempt.lease_token_hash, hash_secret(lease_token)):
        raise HTTPException(status_code=409, detail="Invalid lease token")
    if allow_completed and attempt.status == "succeeded" and task.status == "succeeded":
        return task, attempt
    if task.status != "running" or task.active_attempt_id != attempt.id or task.assigned_node_id != node.id:
        raise HTTPException(status_code=409, detail="Task attempt is no longer active")
    now = _now()
    if (
        task.lease_expires_at is None
        or as_utc(task.lease_expires_at) <= now
        or as_utc(attempt.lease_expires_at) <= now
    ):
        raise HTTPException(status_code=409, detail="Task lease expired")
    return task, attempt


def _transfer_urls(*, object_key: str, proxy_url: str) -> dict[str, Any]:
    if saas_settings.distributed_direct_downloads:
        try:
            signed = object_store.signed_get_url(object_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("Unable to sign direct worker download for %s: %s", object_key, exc)
        else:
            if signed:
                return {
                    "transfer_mode": "direct",
                    "url": signed,
                    "fallback_url": proxy_url,
                    "url_expires_in": saas_settings.storage_signed_url_seconds,
                }
    return {
        "transfer_mode": "proxy",
        "url": proxy_url,
        "fallback_url": None,
        "url_expires_in": None,
    }


def _file_descriptor(asset: Asset, *, task_id: str) -> dict[str, Any]:
    proxy_url = f"{saas_settings.api_prefix}/internal/render/tasks/{task_id}/assets/{asset.id}"
    return {
        "id": asset.id,
        "name": asset.name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        **_transfer_urls(object_key=asset.object_key, proxy_url=proxy_url),
    }


def _artifact_descriptor(artifact: RenderArtifact, *, task_id: str) -> dict[str, Any]:
    proxy_url = f"{saas_settings.api_prefix}/internal/render/tasks/{task_id}/prepared/{artifact.id}"
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        **_transfer_urls(object_key=artifact.object_key, proxy_url=proxy_url),
    }


@internal_router.post("/tasks/claim")
def claim_task(
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not saas_settings.distributed_render_enabled:
        return {"task": None, "reason": "distributed rendering disabled"}
    if node.status not in {"online", "busy"} or not node.accepting_tasks:
        raise HTTPException(status_code=409, detail=f"Worker is not eligible: {node.status}")
    try:
        lease = claim_page_task(db, node_id=node.id)
    except SchedulerError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if lease is None:
        db.commit()
        return {"task": None}
    task = db.get(RenderSubtask, lease.task_id)
    assert task is not None
    assets: list[dict[str, Any]] = []
    for asset_id in sorted(_allowed_asset_ids(db, task)):
        asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == task.tenant_id, Asset.status == "ready"))
        if asset is None:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Required task asset is unavailable: {asset_id}")
        assets.append(_file_descriptor(asset, task_id=task.id))
    prepared: list[dict[str, Any]] = []
    for artifact_id in sorted(_allowed_prepared_artifact_ids(db, task)):
        artifact = db.get(RenderArtifact, artifact_id)
        if artifact is None or artifact.parent_job_id != task.parent_job_id or artifact.status != "ready":
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Prepared task artifact is unavailable: {artifact_id}")
        prepared.append(_artifact_descriptor(artifact, task_id=task.id))
    db.commit()
    return {
        "task": {
            "id": lease.task_id,
            "parent_job_id": lease.parent_job_id,
            "slide_index": lease.slide_index,
            "attempt_id": lease.attempt_id,
            "attempt_no": lease.attempt_no,
            "lease_token": lease.lease_token,
            "lease_expires_at": lease.lease_expires_at.isoformat(),
            "config_hash": lease.config_hash,
            "payload": lease.payload,
            "assets": assets,
            "prepared_artifacts": prepared,
        }
    }


@internal_router.post("/tasks/{task_id}/renew")
def renew_task(
    task_id: str,
    body: LeaseRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    try:
        expiry = renew_lease(
            db,
            task_id=task_id,
            attempt_id=body.attempt_id,
            node_id=node.id,
            lease_token=body.lease_token,
        )
    except LeaseConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"lease_expires_at": expiry.isoformat()}


@internal_router.post("/tasks/{task_id}/progress")
def task_progress(
    task_id: str,
    body: ProgressRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    try:
        report_progress(
            db,
            task_id=task_id,
            attempt_id=body.attempt_id,
            node_id=node.id,
            lease_token=body.lease_token,
            progress=body.progress,
            stage=body.stage,
            metrics=body.metrics,
        )
    except LeaseConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"ok": True}


def _lease_headers(attempt_id: str | None, lease_token: str | None) -> tuple[str, str]:
    if not attempt_id or not lease_token:
        raise HTTPException(status_code=422, detail="X-Attempt-Id and X-Lease-Token headers are required")
    return attempt_id, lease_token


def _parse_http_range(value: str | None, size: int) -> tuple[int, int, bool]:
    if not value:
        return 0, max(0, size - 1), False
    match = _RANGE_RE.match(value.strip())
    if not match:
        raise HTTPException(status_code=416, detail="Invalid Range header")
    first, last = match.groups()
    if not first and not last:
        raise HTTPException(status_code=416, detail="Invalid Range header")
    if first:
        start = int(first)
        end = int(last) if last else size - 1
    else:
        length = int(last)
        start = max(0, size - length)
        end = size - 1
    if start < 0 or start >= size or end < start:
        raise HTTPException(status_code=416, detail="Requested range is not satisfiable")
    return start, min(end, size - 1), True


def _stream_path(path: Path, *, range_header: str | None, content_type: str, background: BackgroundTasks | None = None):
    size = path.stat().st_size
    start, end, partial = _parse_http_range(range_header, size)
    length = end - start + 1

    def iterator() -> Iterator[bytes]:
        with path.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        iterator(),
        status_code=206 if partial else 200,
        media_type=content_type or "application/octet-stream",
        headers=headers,
        background=background,
    )


def _materialized_object(key: str, suffix: str) -> tuple[Path, bool]:
    local = object_store.local_path(key)
    if local is not None:
        return local, False
    fd, name = tempfile.mkstemp(prefix="distributed-download-", suffix=suffix or ".bin")
    os.close(fd)
    path = Path(name)
    object_store.materialize(key, path)
    return path, True


@internal_router.get("/tasks/{task_id}/assets/{asset_id}")
def download_task_asset(
    task_id: str,
    asset_id: str,
    background: BackgroundTasks,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    task, _ = _verify_attempt(db, task_id=task_id, node=node, attempt_id=attempt_id, lease_token=lease_token)
    if asset_id not in _allowed_asset_ids(db, task):
        raise HTTPException(status_code=403, detail="Asset is not assigned to this task")
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == task.tenant_id, Asset.status == "ready"))
    if asset is None:
        raise HTTPException(status_code=404, detail="Task asset not found")
    path, temporary = _materialized_object(asset.object_key, Path(asset.name).suffix)
    if temporary:
        background.add_task(path.unlink, missing_ok=True)
    return _stream_path(path, range_header=range_header, content_type=asset.content_type, background=background)


@internal_router.get("/tasks/{task_id}/prepared/{artifact_id}")
def download_prepared_artifact(
    task_id: str,
    artifact_id: str,
    background: BackgroundTasks,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    task, _ = _verify_attempt(db, task_id=task_id, node=node, attempt_id=attempt_id, lease_token=lease_token)
    if artifact_id not in _allowed_prepared_artifact_ids(db, task):
        raise HTTPException(status_code=403, detail="Prepared artifact is not assigned to this task")
    artifact = db.get(RenderArtifact, artifact_id)
    if artifact is None or artifact.parent_job_id != task.parent_job_id or artifact.status != "ready":
        raise HTTPException(status_code=404, detail="Prepared artifact not found")
    path, temporary = _materialized_object(artifact.object_key, ".bin")
    if temporary:
        background.add_task(path.unlink, missing_ok=True)
    return _stream_path(path, range_header=range_header, content_type=artifact.content_type, background=background)


def _artifact_spec(kind: str) -> tuple[str, str]:
    if kind == "page_video":
        return ".mp4", "video/mp4"
    if kind == "page_audio":
        return ".wav", "audio/wav"
    raise HTTPException(status_code=422, detail="Unsupported artifact kind")


def _artifact_object_key(task: RenderSubtask, attempt: RenderAttempt, kind: str) -> str:
    suffix, _ = _artifact_spec(kind)
    return f"{task.tenant_id}/distributed/{task.parent_job_id}/attempts/{attempt.id}/{kind}{suffix}"


def _existing_attempt_artifact(db: Session, attempt_id: str, kind: str) -> RenderArtifact | None:
    return db.scalar(
        select(RenderArtifact).where(
            RenderArtifact.attempt_id == attempt_id,
            RenderArtifact.kind == kind,
        )
    )


def _record_artifact(
    db: Session,
    *,
    task: RenderSubtask,
    attempt: RenderAttempt,
    kind: str,
    object_key: str,
    size_bytes: int,
    sha256: str,
    transfer_mode: str,
) -> RenderArtifact:
    _, content_type = _artifact_spec(kind)
    artifact = RenderArtifact(
        tenant_id=task.tenant_id,
        parent_job_id=task.parent_job_id,
        subtask_id=task.id,
        attempt_id=attempt.id,
        kind=kind,
        slide_index=task.slide_index,
        object_key=object_key,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        status="ready",
        metadata_json=json.dumps({"transfer_mode": transfer_mode}, sort_keys=True),
    )
    db.add(artifact)
    db.flush()
    return artifact


def _upload_temp_path(task_id: str, attempt_id: str, kind: str) -> Path:
    root = app_settings.workspace_dir / "distributed-uploads" / task_id / attempt_id
    return root / f"{kind}.part"


def _cleanup_upload_temp(path: Path) -> None:
    path.unlink(missing_ok=True)
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break


def _parse_upload_range(value: str | None, body_length: int, current_size: int) -> tuple[int, int, int]:
    if not value:
        start = current_size
        end = start + body_length - 1
        total = end + 1
        return start, end, total
    match = _UPLOAD_RANGE_RE.match(value.strip())
    if not match:
        raise HTTPException(status_code=422, detail="Invalid Content-Range header")
    start, end, total = (int(part) for part in match.groups())
    if end < start or total <= end or body_length != end - start + 1:
        raise HTTPException(status_code=422, detail="Content-Range does not match request body")
    return start, end, total


@internal_router.get("/tasks/{task_id}/artifacts/{kind}/upload")
def upload_status(
    task_id: str,
    kind: str,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
) -> dict[str, Any]:
    if kind not in _ALLOWED_ARTIFACT_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported artifact kind")
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    _, attempt = _verify_attempt(db, task_id=task_id, node=node, attempt_id=attempt_id, lease_token=lease_token)
    existing = _existing_attempt_artifact(db, attempt.id, kind)
    if existing is not None:
        return {"completed": True, "received_bytes": existing.size_bytes, "sha256": existing.sha256}
    path = _upload_temp_path(task_id, attempt_id, kind)
    return {"completed": False, "received_bytes": path.stat().st_size if path.exists() else 0}


@internal_router.post("/tasks/{task_id}/artifacts/{kind}/direct-upload")
def begin_direct_artifact_upload(
    task_id: str,
    kind: str,
    body: DirectUploadRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
) -> dict[str, Any]:
    if kind not in _ALLOWED_ARTIFACT_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported artifact kind")
    if body.size_bytes > saas_settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Artifact exceeds configured upload limit")
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    task, attempt = _verify_attempt(
        db,
        task_id=task_id,
        node=node,
        attempt_id=attempt_id,
        lease_token=lease_token,
    )
    existing = _existing_attempt_artifact(db, attempt.id, kind)
    digest = body.sha256.lower()
    if existing is not None:
        if existing.size_bytes == body.size_bytes and hmac.compare_digest(existing.sha256, digest):
            return {
                "mode": "completed",
                "completed": True,
                "artifact_id": existing.id,
                "received_bytes": existing.size_bytes,
                "sha256": existing.sha256,
            }
        raise HTTPException(status_code=409, detail="Artifact already finalized for this attempt")
    if not saas_settings.distributed_direct_uploads:
        return {"mode": "proxy", "completed": False}

    key = _artifact_object_key(task, attempt, kind)
    try:
        signed = object_store.signed_put_url(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("Unable to sign direct worker upload for %s: %s", key, exc)
        signed = None
    if not signed:
        return {"mode": "proxy", "completed": False}
    return {
        "mode": "direct",
        "completed": False,
        "upload_url": signed,
        "object_key": key,
        "expires_in": saas_settings.storage_signed_url_seconds,
    }


@internal_router.post("/tasks/{task_id}/artifacts/{kind}/direct-commit")
def commit_direct_artifact_upload(
    task_id: str,
    kind: str,
    body: DirectUploadCommitRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
) -> dict[str, Any]:
    if kind not in _ALLOWED_ARTIFACT_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported artifact kind")
    if body.size_bytes > saas_settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Artifact exceeds configured upload limit")
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    task, attempt = _verify_attempt(
        db,
        task_id=task_id,
        node=node,
        attempt_id=attempt_id,
        lease_token=lease_token,
    )
    digest = body.sha256.lower()
    existing = _existing_attempt_artifact(db, attempt.id, kind)
    if existing is not None:
        if existing.size_bytes == body.size_bytes and hmac.compare_digest(existing.sha256, digest):
            return {
                "completed": True,
                "artifact_id": existing.id,
                "received_bytes": existing.size_bytes,
                "sha256": existing.sha256,
                "idempotent": True,
            }
        raise HTTPException(status_code=409, detail="Artifact already finalized for this attempt")

    expected_key = _artifact_object_key(task, attempt, kind)
    if not hmac.compare_digest(body.object_key, expected_key):
        raise HTTPException(status_code=409, detail="Direct upload object key mismatch")
    try:
        remote_size = object_store.object_size(expected_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("Unable to HEAD direct worker upload %s: %s", expected_key, exc)
        raise HTTPException(status_code=503, detail="Unable to verify direct upload") from exc
    if remote_size is None:
        raise HTTPException(status_code=409, detail="Direct upload object is not available")
    if remote_size != body.size_bytes:
        try:
            object_store.delete(expected_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("Unable to remove invalid direct upload %s: %s", expected_key, exc)
        raise HTTPException(
            status_code=422,
            detail=f"Direct upload size mismatch: object={remote_size} expected={body.size_bytes}",
        )

    artifact = _record_artifact(
        db,
        task=task,
        attempt=attempt,
        kind=kind,
        object_key=expected_key,
        size_bytes=body.size_bytes,
        sha256=digest,
        transfer_mode="direct",
    )
    db.commit()
    _cleanup_upload_temp(_upload_temp_path(task_id, attempt_id, kind))
    return {
        "completed": True,
        "artifact_id": artifact.id,
        "received_bytes": body.size_bytes,
        "sha256": digest,
    }


@internal_router.put("/tasks/{task_id}/artifacts/{kind}")
async def upload_artifact_chunk(
    task_id: str,
    kind: str,
    request: Request,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
    x_attempt_id: Annotated[str | None, Header(alias="X-Attempt-Id")] = None,
    x_lease_token: Annotated[str | None, Header(alias="X-Lease-Token")] = None,
    x_content_sha256: Annotated[str | None, Header(alias="X-Content-SHA256")] = None,
    content_range: Annotated[str | None, Header(alias="Content-Range")] = None,
) -> dict[str, Any]:
    if kind not in _ALLOWED_ARTIFACT_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported artifact kind")
    attempt_id, lease_token = _lease_headers(x_attempt_id, x_lease_token)
    task, attempt = _verify_attempt(db, task_id=task_id, node=node, attempt_id=attempt_id, lease_token=lease_token)
    existing = db.scalar(select(RenderArtifact).where(RenderArtifact.attempt_id == attempt.id, RenderArtifact.kind == kind))
    if existing is not None:
        if x_content_sha256 and hmac.compare_digest(existing.sha256, x_content_sha256.lower()):
            return {"completed": True, "artifact_id": existing.id, "received_bytes": existing.size_bytes, "sha256": existing.sha256}
        raise HTTPException(status_code=409, detail="Artifact already finalized for this attempt")

    body = await request.body()
    path = _upload_temp_path(task_id, attempt_id, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.stat().st_size if path.exists() else 0
    start, end, total = _parse_upload_range(content_range, len(body), current)
    if start != current:
        raise HTTPException(status_code=409, detail={"message": "Upload offset mismatch", "received_bytes": current})
    if total > saas_settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Artifact exceeds configured upload limit")
    with path.open("ab") as fh:
        fh.write(body)
    received = path.stat().st_size
    if received < total:
        return {"completed": False, "received_bytes": received, "total_bytes": total}
    if received != total:
        _cleanup_upload_temp(path)
        raise HTTPException(status_code=422, detail="Uploaded artifact exceeds declared size")
    if not x_content_sha256 or len(x_content_sha256.strip()) != 64:
        raise HTTPException(status_code=422, detail="X-Content-SHA256 is required on the final chunk")
    digest = _sha256_path(path)
    if not hmac.compare_digest(digest, x_content_sha256.strip().lower()):
        _cleanup_upload_temp(path)
        raise HTTPException(status_code=422, detail="Artifact SHA-256 mismatch")

    key = _artifact_object_key(task, attempt, kind)
    uri = object_store.put_file(path, key)
    del uri
    artifact = _record_artifact(
        db,
        task=task,
        attempt=attempt,
        kind=kind,
        object_key=key,
        size_bytes=received,
        sha256=digest,
        transfer_mode="proxy",
    )
    db.commit()
    _cleanup_upload_temp(path)
    return {"completed": True, "artifact_id": artifact.id, "received_bytes": received, "sha256": digest}


def _completed_idempotently(db: Session, *, task_id: str, attempt_id: str, node_id: str, lease_token: str) -> bool:
    task = db.get(RenderSubtask, task_id)
    attempt = db.get(RenderAttempt, attempt_id)
    if task is None or attempt is None:
        return False
    return bool(
        task.status == "succeeded"
        and attempt.status == "succeeded"
        and attempt.subtask_id == task.id
        and attempt.node_id == node_id
        and hmac.compare_digest(attempt.lease_token_hash, hash_secret(lease_token))
    )


@internal_router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    body: CompleteRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if _completed_idempotently(
        db,
        task_id=task_id,
        attempt_id=body.attempt_id,
        node_id=node.id,
        lease_token=body.lease_token,
    ):
        return {"ok": True, "idempotent": True}
    task, attempt = _verify_attempt(
        db,
        task_id=task_id,
        node=node,
        attempt_id=body.attempt_id,
        lease_token=body.lease_token,
    )
    artifacts = db.scalars(select(RenderArtifact).where(RenderArtifact.attempt_id == attempt.id, RenderArtifact.status == "ready")).all()
    by_kind = {item.kind: item for item in artifacts}
    missing = sorted(_ALLOWED_ARTIFACT_KINDS - set(by_kind))
    if missing:
        raise HTTPException(status_code=409, detail=f"Required page artifacts missing: {', '.join(missing)}")
    required_media = {"video_seconds", "audio_seconds", "frame_count", "encoding"}
    missing_media = sorted(key for key in required_media if key not in body.media)
    if missing_media:
        raise HTTPException(status_code=422, detail=f"Required media metadata missing: {', '.join(missing_media)}")
    metadata = {"media": body.media, "metrics": body.metrics}
    for artifact in artifacts:
        existing_metadata = _json(artifact.metadata_json, {})
        artifact.metadata_json = json.dumps(
            {
                **(existing_metadata if isinstance(existing_metadata, dict) else {}),
                **metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    try:
        finalize_queued = complete_page_task(
            db,
            task_id=task.id,
            attempt_id=attempt.id,
            node_id=node.id,
            lease_token=body.lease_token,
            metrics={**body.metrics, "media": body.media},
        )
    except LeaseConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"ok": True, "finalize_queued": finalize_queued}


@internal_router.post("/tasks/{task_id}/fail")
def fail_task(
    task_id: str,
    body: FailRequest,
    node: Annotated[WorkerNode, Depends(get_worker_node)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    attempt = db.get(RenderAttempt, body.attempt_id)
    task = db.get(RenderSubtask, task_id)
    if attempt is not None and task is not None and attempt.subtask_id == task.id and attempt.node_id == node.id:
        if attempt.status in {"failed", "expired"} and task.status in {"retry_wait", "failed"}:
            if hmac.compare_digest(attempt.lease_token_hash, hash_secret(body.lease_token)):
                return {"ok": True, "idempotent": True, "retried": task.status == "retry_wait"}
    try:
        retried = fail_page_task(
            db,
            task_id=task_id,
            attempt_id=body.attempt_id,
            node_id=node.id,
            lease_token=body.lease_token,
            error=body.error,
            retryable=body.retryable,
            metrics=body.metrics,
        )
    except LeaseConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"ok": True, "retried": retried}
