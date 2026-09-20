from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auxiliary_task_models import AuxiliaryTaskLease
from .database import get_db
from .distributed_render_models import (
    RenderAttempt,
    RenderSubtask,
    WorkerHeartbeatSample,
    WorkerNode,
)
from .models import RenderJobRecord
from .security import Principal, require_superuser
from .settings import saas_settings
from .worker_status_api import _legacy_status


router = APIRouter(prefix="/admin/workers", tags=["admin-worker-management"])


class WorkerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    group_name: str | None = Field(default=None, max_length=80)
    slots_total: int | None = Field(default=None, ge=1, le=4)
    notes: str | None = Field(default=None, max_length=2000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def _node_runtime_state(node: WorkerNode, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    seen = _utc(node.last_seen_at)
    heartbeat_age = (now - seen).total_seconds() if seen else None
    online_window = max(30, saas_settings.distributed_lease_seconds)
    online = bool(
        seen
        and heartbeat_age is not None
        and heartbeat_age <= online_window
        and node.status not in {"revoked", "incompatible", "pending"}
    )
    if node.status in {"revoked", "incompatible", "pending"}:
        effective_status = node.status
    elif not online:
        effective_status = "offline"
    elif node.status == "disk_low":
        effective_status = "disk_low"
    elif not node.accepting_tasks:
        effective_status = "draining"
    elif node.slots_busy:
        effective_status = "busy"
    else:
        effective_status = "online"
    return {
        "online": online,
        "effective_status": effective_status,
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
    }


def _serialize_node(node: WorkerNode, *, now: datetime | None = None) -> dict[str, Any]:
    runtime = _node_runtime_state(node, now=now)
    return {
        "id": node.id,
        "name": node.name,
        "group_name": node.group_name or "default",
        "notes": node.notes or "",
        "status": node.status,
        **runtime,
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
        "cpu_percent": node.cpu_percent,
        "memory_percent": node.memory_percent,
        "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def _duration_seconds(started: datetime | None, completed: datetime | None, *, now: datetime) -> float | None:
    start = _utc(started)
    end = _utc(completed) or now
    if start is None:
        return None
    return max(0.0, round((end - start).total_seconds(), 1))


def _attempt_payload(
    attempt: RenderAttempt,
    task: RenderSubtask,
    jobs: dict[str, RenderJobRecord],
    *,
    now: datetime,
) -> dict[str, Any]:
    job = jobs.get(task.parent_job_id)
    return {
        "attempt_id": attempt.id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "progress": attempt.progress,
        "stage": attempt.stage,
        "error": attempt.error,
        "metrics": _json(attempt.metrics_json, {}),
        "claimed_at": attempt.claimed_at.isoformat() if attempt.claimed_at else None,
        "last_renewed_at": attempt.last_renewed_at.isoformat() if attempt.last_renewed_at else None,
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
        "duration_seconds": _duration_seconds(attempt.claimed_at, attempt.completed_at, now=now),
        "task": {
            "id": task.id,
            "task_type": task.task_type,
            "slide_index": task.slide_index,
            "status": task.status,
            "progress": task.progress,
            "stage": task.stage,
            "parent_job_id": task.parent_job_id,
            "error": task.error,
        },
        "parent_job": (
            {
                "id": job.id,
                "course_id": job.course_id,
                "engine": job.engine,
                "status": job.status,
                "progress": job.progress,
                "stage": job.stage,
            }
            if job is not None
            else None
        ),
    }


def _period_stats(db: Session, node_id: str, *, since: datetime, now: datetime) -> dict[str, Any]:
    attempts = db.scalars(
        select(RenderAttempt)
        .where(RenderAttempt.node_id == node_id, RenderAttempt.claimed_at >= since)
        .order_by(RenderAttempt.claimed_at.desc())
    ).all()
    succeeded = [item for item in attempts if item.status == "succeeded"]
    failed = [item for item in attempts if item.status == "failed"]
    running = [item for item in attempts if item.status == "running"]
    durations = [
        value
        for item in succeeded
        if (value := _duration_seconds(item.claimed_at, item.completed_at, now=now)) is not None
    ]
    terminal = len(succeeded) + len(failed)
    return {
        "attempts": len(attempts),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "running": len(running),
        "success_rate": round(len(succeeded) / max(1, terminal) * 100, 1),
        "average_success_seconds": round(sum(durations) / len(durations), 1) if durations else None,
    }


@router.get("/overview")
def worker_overview(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    now = _now()
    nodes = db.scalars(select(WorkerNode).order_by(WorkerNode.created_at.asc())).all()
    workers = [_serialize_node(node, now=now) for node in nodes]
    statuses = [item["effective_status"] for item in workers]
    queued_tasks = int(
        db.scalar(
            select(func.count())
            .select_from(RenderSubtask)
            .where(RenderSubtask.task_type == "page", RenderSubtask.status == "queued")
        )
        or 0
    )
    running_attempts = int(
        db.scalar(
            select(func.count())
            .select_from(RenderAttempt)
            .where(RenderAttempt.status == "running")
        )
        or 0
    )
    since = now - timedelta(hours=24)
    completed_24h = int(
        db.scalar(
            select(func.count())
            .select_from(RenderAttempt)
            .where(RenderAttempt.status == "succeeded", RenderAttempt.completed_at >= since)
        )
        or 0
    )
    failed_24h = int(
        db.scalar(
            select(func.count())
            .select_from(RenderAttempt)
            .where(RenderAttempt.status == "failed", RenderAttempt.completed_at >= since)
        )
        or 0
    )
    legacy_engines = _legacy_status()
    legacy_online_count = sum(
        int(item.get("count") or 0)
        for item in legacy_engines.values()
        if item.get("online")
    )

    groups: dict[str, dict[str, int]] = {}
    for worker in workers:
        group = str(worker.get("group_name") or "default")
        bucket = groups.setdefault(group, {"total": 0, "online": 0, "busy": 0, "warning": 0})
        bucket["total"] += 1
        if worker["online"]:
            bucket["online"] += 1
        if worker["effective_status"] == "busy":
            bucket["busy"] += 1
        if worker["effective_status"] in {"disk_low", "incompatible"}:
            bucket["warning"] += 1

    return {
        "render_contract_version": saas_settings.render_contract_version,
        "legacy_engines": legacy_engines,
        "groups": groups,
        "summary": {
            "total": len(workers),
            "visible_total": len(workers) + legacy_online_count,
            "legacy_online": legacy_online_count,
            "registered": sum(
                1 for item in workers if item["effective_status"] not in {"revoked", "pending"}
            ),
            "online": sum(1 for item in workers if item["online"]),
            "busy": statuses.count("busy"),
            "draining": statuses.count("draining"),
            "offline": statuses.count("offline"),
            "warning": sum(1 for status in statuses if status in {"disk_low", "incompatible"}),
            "pending": statuses.count("pending"),
            "slots_total": sum(
                int(item["slots_total"] or 0)
                for item in workers
                if item["effective_status"] != "revoked"
            ),
            "slots_busy": sum(
                int(item["slots_busy"] or 0)
                for item in workers
                if item["effective_status"] != "revoked"
            ),
            "queued_tasks": queued_tasks,
            "running_attempts": running_attempts,
            "completed_24h": completed_24h,
            "failed_24h": failed_24h,
        },
        "workers": workers,
    }


@router.patch("/{node_id}")
def update_worker(
    node_id: str,
    body: WorkerUpdateRequest,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node = db.get(WorkerNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Worker node not found")
    if body.name is not None:
        node.name = body.name.strip()
    if body.group_name is not None:
        node.group_name = body.group_name.strip() or "default"
    if body.slots_total is not None:
        if body.slots_total < node.slots_busy:
            raise HTTPException(
                status_code=409,
                detail=f"Worker currently uses {node.slots_busy} slots; slots_total cannot be lower",
            )
        node.slots_total = body.slots_total
    if body.notes is not None:
        node.notes = body.notes.strip()
    db.commit()
    db.refresh(node)
    return _serialize_node(node)


@router.get("/{node_id}")
def worker_detail(
    node_id: str,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del principal
    node = db.get(WorkerNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Worker node not found")

    now = _now()
    rows = db.execute(
        select(RenderAttempt, RenderSubtask)
        .join(RenderSubtask, RenderSubtask.id == RenderAttempt.subtask_id)
        .where(RenderAttempt.node_id == node_id)
        .order_by(RenderAttempt.claimed_at.desc())
        .limit(100)
    ).all()
    parent_ids = {task.parent_job_id for _attempt, task in rows}
    jobs = {
        job.id: job
        for job in (
            db.scalars(select(RenderJobRecord).where(RenderJobRecord.id.in_(parent_ids))).all()
            if parent_ids
            else []
        )
    }
    recent_attempts = [
        _attempt_payload(attempt, task, jobs, now=now)
        for attempt, task in rows
    ]
    auxiliary = db.scalars(
        select(AuxiliaryTaskLease)
        .where(AuxiliaryTaskLease.node_id == node_id)
        .order_by(AuxiliaryTaskLease.created_at.desc())
        .limit(20)
    ).all()

    samples = db.scalars(
        select(WorkerHeartbeatSample)
        .where(
            WorkerHeartbeatSample.node_id == node_id,
            WorkerHeartbeatSample.created_at >= now - timedelta(hours=2),
        )
        .order_by(WorkerHeartbeatSample.created_at.asc())
        .limit(240)
    ).all()

    return {
        "worker": _serialize_node(node, now=now),
        "stats_24h": _period_stats(db, node_id, since=now - timedelta(hours=24), now=now),
        "stats_7d": _period_stats(db, node_id, since=now - timedelta(days=7), now=now),
        "active_auxiliary_tasks": [
            {
                "lease_id": lease.id,
                "kind": lease.kind,
                "job_id": lease.job_id,
                "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
                "created_at": lease.created_at.isoformat() if lease.created_at else None,
            }
            for lease in auxiliary
            if (_utc(lease.expires_at) or now) > now
        ],
        "health_series": [
            {
                "created_at": sample.created_at.isoformat() if sample.created_at else None,
                "status": sample.status,
                "slots_busy": sample.slots_busy,
                "current_task_id": sample.current_task_id,
                "cpu_percent": sample.cpu_percent,
                "memory_percent": sample.memory_percent,
                "memory_available_mb": sample.memory_available_mb,
                "disk_free_bytes": sample.disk_free_bytes,
            }
            for sample in samples
        ],
        "recent_attempts": recent_attempts,
    }
