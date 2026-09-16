from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Course, RenderJobRecord
from .security import Principal, get_principal
from .settings import saas_settings


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _payload(item: RenderJobRecord) -> dict:
    try:
        return json.loads(item.payload_json or "{}")
    except Exception:
        return {}


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
