from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .distributed_render_models import RenderSubtask, WorkerNode
from .models import Course, RenderJobRecord
from .security import Principal, get_principal
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
