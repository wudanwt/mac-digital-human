from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .distributed_render_models import RenderAttempt, RenderSubtask, WorkerNode
from .models import Course, RenderJobRecord
from .queue import job_queue
from .security import Principal, get_principal
from .services import audit, refund_render_seconds
from .settings import saas_settings


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _payload(item: RenderJobRecord) -> dict:
    try:
        value = json.loads(item.payload_json or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _distributed_tasks(db: Session, job_id: str) -> list[dict]:
    tasks = db.scalars(
        select(RenderSubtask)
        .where(RenderSubtask.parent_job_id == job_id)
        .order_by(
            RenderSubtask.task_type.asc(),
            RenderSubtask.slide_index.asc(),
            RenderSubtask.created_at.asc(),
        )
    ).all()
    if not tasks:
        return []
    node_ids = {task.assigned_node_id for task in tasks if task.assigned_node_id}
    nodes = {
        node.id: node
        for node in db.scalars(select(WorkerNode).where(WorkerNode.id.in_(node_ids))).all()
    } if node_ids else {}
    result: list[dict] = []
    for task in tasks:
        node = nodes.get(task.assigned_node_id) if task.assigned_node_id else None
        result.append(
            {
                "id": task.id,
                "type": task.task_type,
                "slide_index": task.slide_index,
                "status": task.status,
                "progress": task.progress,
                "stage": task.stage,
                "attempt_count": task.attempt_count,
                "estimated_seconds": task.estimated_seconds,
                "blocked_reason": task.blocked_reason,
                "error": task.error,
                "node": (
                    {
                        "id": node.id,
                        "name": node.name,
                        "status": node.status,
                        "host": node.host,
                        "machine": node.machine,
                    }
                    if node
                    else None
                ),
                "lease_expires_at": task.lease_expires_at.isoformat() if task.lease_expires_at else None,
                "available_at": task.available_at.isoformat() if task.available_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            }
        )
    return result


def _distributed_summary(tasks: list[dict]) -> dict | None:
    if not tasks:
        return None
    pages = [task for task in tasks if task["type"] == "page"]
    return {
        "enabled_for_job": True,
        "page_count": len(pages),
        "pages_succeeded": sum(task["status"] == "succeeded" for task in pages),
        "pages_running": sum(task["status"] == "running" for task in pages),
        "pages_queued": sum(task["status"] in {"queued", "retry_wait", "blocked"} for task in pages),
        "pages_failed": sum(task["status"] == "failed" for task in pages),
        "retry_attempts": sum(max(0, int(task["attempt_count"] or 0) - 1) for task in pages),
    }


def _job_response(item: RenderJobRecord, *, course: Course | None, tasks: list[dict], runtime: dict) -> dict:
    return {
        "id": item.id,
        "course_id": item.course_id,
        "course_title": course.title if course else None,
        "engine": item.engine,
        "status": item.status,
        "progress": item.progress,
        "stage": item.stage,
        "error": item.error,
        "estimated_seconds": item.estimated_seconds,
        "video_seconds": item.video_seconds,
        "gpu_seconds": item.gpu_seconds,
        "queue_wait_seconds": item.queue_wait_seconds,
        "runtime": runtime,
        "distributed": _distributed_summary(tasks),
        "tasks": tasks,
        "output_asset_id": item.output_asset_id,
        "output_download_url": (
            f"{saas_settings.api_prefix}/assets/{item.output_asset_id}/download"
            if item.output_asset_id
            else None
        ),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


@router.get("/{job_id}/detail")
def job_detail(
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
    course = db.get(Course, item.course_id) if item.course_id else None
    if course is not None and course.tenant_id != principal.tenant_id:
        course = None
    payload = _payload(item)
    runtime = payload.get("_runtime") or {}
    tasks = _distributed_tasks(db, item.id)
    return _job_response(item, course=course, tasks=tasks, runtime=runtime)


@router.post("/{job_id}/cancel")
def cancel_job_with_distributed_support(
    job_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Cancel either a legacy whole-course job or a live page-task graph.

    This router is mounted before the legacy studio job router, so it upgrades the
    historical queued-only cancellation endpoint without changing its public URL.
    Active remote attempts are invalidated transactionally; their next renew or
    progress report receives a lease conflict and cannot publish stale output.
    """

    item = db.scalar(
        select(RenderJobRecord)
        .where(
            RenderJobRecord.id == job_id,
            RenderJobRecord.tenant_id == principal.tenant_id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if item.user_id != principal.user_id and principal.role not in {"owner", "admin"} and not principal.is_superuser:
        raise HTTPException(status_code=403, detail="You cannot cancel this job")
    if item.status == "canceled":
        course = db.get(Course, item.course_id) if item.course_id else None
        tasks = _distributed_tasks(db, item.id)
        return _job_response(item, course=course, tasks=tasks, runtime=_payload(item).get("_runtime") or {})
    if item.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Only queued or running jobs can be canceled")

    now = datetime.now(timezone.utc)
    subtasks = db.scalars(
        select(RenderSubtask)
        .where(RenderSubtask.parent_job_id == item.id)
        .with_for_update()
    ).all()
    node_ids: set[str] = set()
    for task in subtasks:
        if task.status in {"succeeded", "failed", "canceled"}:
            continue
        if task.assigned_node_id:
            node_ids.add(task.assigned_node_id)
        if task.active_attempt_id:
            attempt = db.get(RenderAttempt, task.active_attempt_id)
            if attempt and attempt.status == "running":
                attempt.status = "canceled"
                attempt.error = "parent render canceled"
                attempt.completed_at = now
        task.status = "canceled"
        task.stage = "canceled"
        task.error = "parent render canceled"
        task.completed_at = now
        task.available_at = None
        task.lease_expires_at = None
        task.active_attempt_id = None
        task.assigned_node_id = None

    for node_id in node_ids:
        node = db.scalar(select(WorkerNode).where(WorkerNode.id == node_id).with_for_update())
        if node is None:
            continue
        node.slots_busy = max(0, int(node.slots_busy or 0) - 1)
        if node.current_task_id and any(task.id == node.current_task_id for task in subtasks):
            node.current_task_id = None
        if node.status not in {"revoked", "incompatible", "disk_low"}:
            node.status = "online" if node.accepting_tasks else "draining"

    item.status = "canceled"
    item.stage = "canceled"
    item.error = None
    item.completed_at = now
    refund_render_seconds(
        db,
        tenant_id=item.tenant_id,
        user_id=item.user_id,
        job_id=item.id,
        seconds=item.estimated_seconds,
    )
    course = db.get(Course, item.course_id) if item.course_id else None
    if course and course.tenant_id == principal.tenant_id and course.status != "completed":
        course.status = "draft"
    audit(
        db,
        action="render.cancel",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="job",
        target_id=item.id,
        details={"distributed_subtasks": len(subtasks), "previous_status": "running" if item.started_at else "queued"},
    )
    db.commit()

    # Legacy Redis cancellation remains best effort. Distributed parents are not
    # enqueued there, while old queued jobs retain the historical behavior.
    try:
        job_queue.cancel(item.id)
    except Exception:
        pass

    db.refresh(item)
    tasks = _distributed_tasks(db, item.id)
    return _job_response(item, course=course, tasks=tasks, runtime=_payload(item).get("_runtime") or {})
