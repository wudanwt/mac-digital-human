from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .avatar_matting_models import AvatarMattingJob
from .models import Asset, Avatar
from .settings import saas_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def matting_model_name() -> str:
    return (os.getenv("AVATAR_MATTING_MODEL", "birefnet-portrait").strip() or "birefnet-portrait")[:120]


def _asset_dict(asset: Asset | None) -> dict[str, Any] | None:
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


def latest_matting_job(db: Session, avatar: Avatar, *, source_only: bool = True) -> AvatarMattingJob | None:
    query = select(AvatarMattingJob).where(
        AvatarMattingJob.tenant_id == avatar.tenant_id,
        AvatarMattingJob.avatar_id == avatar.id,
    )
    if source_only and avatar.master_video_asset_id:
        query = query.where(AvatarMattingJob.source_asset_id == avatar.master_video_asset_id)
    return db.scalar(query.order_by(AvatarMattingJob.created_at.desc()).limit(1))


def ready_matting_assets(db: Session, avatar: Avatar) -> tuple[Asset | None, Asset | None, Asset | None, AvatarMattingJob | None]:
    job = latest_matting_job(db, avatar)
    if job is None or job.status != "succeeded" or job.source_asset_id != avatar.master_video_asset_id:
        return None, None, None, job
    alpha = db.get(Asset, job.alpha_asset_id) if job.alpha_asset_id else None
    poster = db.get(Asset, job.poster_asset_id) if job.poster_asset_id else None
    white = db.get(Asset, job.white_preview_asset_id) if job.white_preview_asset_id else None
    if alpha is None or poster is None:
        return None, poster, white, job
    return alpha, poster, white, job


def matting_status_dict(db: Session, avatar: Avatar) -> dict[str, Any]:
    alpha, poster, white, job = ready_matting_assets(db, avatar)
    if job is None:
        return {
            "status": "unprocessed",
            "progress": 0,
            "stage": "not_started",
            "model": matting_model_name(),
            "transparent_ready": False,
            "alpha_asset": None,
            "poster_asset": None,
            "white_preview_asset": None,
            "error": None,
            "metadata": {},
            "source_asset_id": avatar.master_video_asset_id,
            "job_id": None,
        }
    try:
        metadata = json.loads(job.metadata_json or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
    except Exception:
        metadata = {}
    return {
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "model": job.model,
        "transparent_ready": bool(alpha and poster and job.status == "succeeded"),
        "alpha_asset": _asset_dict(alpha),
        "poster_asset": _asset_dict(poster),
        "white_preview_asset": _asset_dict(white),
        "error": job.error,
        "metadata": metadata,
        "source_asset_id": job.source_asset_id,
        "job_id": job.id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def queue_matting_job(
    db: Session,
    avatar: Avatar,
    *,
    user_id: str,
    force: bool = False,
) -> AvatarMattingJob:
    if not avatar.master_video_asset_id:
        raise ValueError("digital human has no master video")

    latest = latest_matting_job(db, avatar)
    if latest and not force:
        if latest.status in {"queued", "running"}:
            return latest
        if latest.status == "succeeded":
            alpha, poster, _, _ = ready_matting_assets(db, avatar)
            if alpha is not None and poster is not None:
                return latest

    job = AvatarMattingJob(
        tenant_id=avatar.tenant_id,
        user_id=user_id,
        avatar_id=avatar.id,
        source_asset_id=avatar.master_video_asset_id,
        status="queued",
        progress=0,
        stage="queued",
        model=matting_model_name(),
        metadata_json="{}",
        error=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(job)
    db.flush()
    return job
