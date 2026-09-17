from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

from ..config import settings
from .avatar_matting_engine import PortraitMattingEngine
from .avatar_matting_models import AvatarMattingJob
from .database import SessionLocal
from .models import Asset, Avatar
from .services import audit, enforce_storage_limit
from .storage import object_store


log = logging.getLogger("digital-human.saas.avatar-matting")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recover_stale_avatar_matting(*, stale_after_minutes: int = 10) -> int:
    """Release jobs left running after a Mac Worker exit or restart."""
    now = _now()
    cutoff = now - timedelta(minutes=stale_after_minutes)
    with SessionLocal() as db:
        result = db.execute(
            update(AvatarMattingJob)
            .where(
                AvatarMattingJob.status == "running",
                AvatarMattingJob.updated_at < cutoff,
            )
            .values(
                status="failed",
                stage="interrupted",
                error="Mac Worker 重启或退出导致任务中断，请重新生成透明资产。",
                completed_at=now,
                updated_at=now,
            )
        )
        db.commit()
        return int(result.rowcount or 0)


def _claim_job() -> str | None:
    """Claim one queued job using a row lock so multiple Mac workers are safe."""
    with SessionLocal() as db:
        query = (
            select(AvatarMattingJob)
            .where(AvatarMattingJob.status == "queued")
            .order_by(AvatarMattingJob.created_at.asc())
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
        job.progress = max(1, job.progress)
        job.stage = "starting"
        job.error = None
        job.started_at = _now()
        job.updated_at = _now()
        db.commit()
        return job.id


def _update(job_id: str, progress: int, stage: str) -> None:
    with SessionLocal() as db:
        job = db.get(AvatarMattingJob, job_id)
        if job is None or job.status != "running":
            return
        job.progress = max(job.progress, min(99, int(progress)))
        job.stage = stage[:80]
        job.updated_at = _now()
        db.commit()


def _generated_asset(db, job: AvatarMattingJob, path: Path, *, kind: str, content_type: str, suffix: str) -> tuple[Asset, str]:
    key = f"{job.tenant_id}/avatar-matting/{job.avatar_id}/{job.id}/{uuid4().hex}{suffix}"
    uri = object_store.put_file(path, key)
    asset = Asset(
        tenant_id=job.tenant_id,
        user_id=job.user_id,
        kind=kind,
        name=f"{job.avatar_id}-{kind}{suffix}",
        object_key=key,
        uri=uri,
        content_type=content_type,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
        status="ready",
    )
    db.add(asset)
    db.flush()
    return asset, key


def process_one_avatar_matting() -> bool:
    job_id = _claim_job()
    if not job_id:
        return False

    work = settings.workspace_dir / "saas-matting" / job_id
    work.mkdir(parents=True, exist_ok=True)
    created_keys: list[str] = []
    try:
        with SessionLocal() as db:
            job = db.get(AvatarMattingJob, job_id)
            if job is None:
                return True
            avatar = db.scalar(
                select(Avatar).where(Avatar.id == job.avatar_id, Avatar.tenant_id == job.tenant_id)
            )
            if avatar is None:
                raise RuntimeError("digital human was deleted before matting started")
            if avatar.master_video_asset_id != job.source_asset_id:
                job.status = "canceled"
                job.stage = "superseded"
                job.progress = 100
                job.error = "master video was replaced; this matting job is obsolete"
                job.completed_at = _now()
                job.updated_at = _now()
                db.commit()
                return True
            source = db.scalar(
                select(Asset).where(Asset.id == job.source_asset_id, Asset.tenant_id == job.tenant_id)
            )
            if source is None:
                raise RuntimeError("master video asset is missing")
            suffix = Path(source.name).suffix.lower() or ".mp4"
            source_path = object_store.materialize(source.object_key, work / f"source{suffix}")
            model = job.model

        engine = PortraitMattingEngine(model=model)
        result = engine.process(source_path, work, progress=lambda pct, detail: _update(job_id, pct, detail))
        total_bytes = result.alpha_video.stat().st_size + result.poster_png.stat().st_size + result.white_preview.stat().st_size

        with SessionLocal() as db:
            job = db.get(AvatarMattingJob, job_id)
            if job is None:
                raise RuntimeError("matting job disappeared")
            avatar = db.get(Avatar, job.avatar_id)
            if avatar is None or avatar.master_video_asset_id != job.source_asset_id:
                job.status = "canceled"
                job.stage = "superseded"
                job.progress = 100
                job.error = "master video changed while matting was running"
                job.completed_at = _now()
                db.commit()
                return True

            enforce_storage_limit(db, job.tenant_id, incoming_bytes=total_bytes)
            alpha, key = _generated_asset(db, job, result.alpha_video, kind="avatar_alpha", content_type="video/mp4", suffix=".mp4")
            created_keys.append(key)
            poster, key = _generated_asset(db, job, result.poster_png, kind="avatar_cutout", content_type="image/png", suffix=".png")
            created_keys.append(key)
            white, key = _generated_asset(db, job, result.white_preview, kind="avatar_white", content_type="video/mp4", suffix=".mp4")
            created_keys.append(key)

            job.alpha_asset_id = alpha.id
            job.poster_asset_id = poster.id
            job.white_preview_asset_id = white.id
            job.status = "succeeded"
            job.progress = 100
            job.stage = "completed"
            job.error = None
            job.metadata_json = json.dumps(
                {
                    "fps": round(result.fps, 6),
                    "frames": result.frame_count,
                    "width": result.width,
                    "height": result.height,
                    "model": result.model,
                    "backend": result.backend,
                    "foreground_recovery": result.foreground_recovery,
                    "foreground_recovered_ratio": round(result.foreground_recovered_ratio, 4),
                    "green_screen": result.green_screen,
                    "elapsed_seconds": round(result.elapsed_seconds, 2),
                    "temporal_smoothing": engine.temporal_smoothing,
                    "edge_blur": engine.edge_blur,
                },
                ensure_ascii=False,
            )
            job.completed_at = _now()
            job.updated_at = _now()
            audit(
                db,
                action="avatar.matting.completed",
                tenant_id=job.tenant_id,
                user_id=job.user_id,
                target_type="avatar",
                target_id=job.avatar_id,
                details={"job_id": job.id, "alpha_asset_id": alpha.id, "poster_asset_id": poster.id, "white_asset_id": white.id},
            )
            db.commit()
        log.info("Avatar matting completed job=%s frames=%s model=%s", job_id, result.frame_count, result.model)
    except Exception as exc:  # noqa: BLE001
        log.exception("Avatar matting failed job=%s", job_id)
        for key in created_keys:
            try:
                object_store.delete(key)
            except Exception:
                pass
        with SessionLocal() as db:
            job = db.get(AvatarMattingJob, job_id)
            if job and job.status not in {"canceled", "succeeded"}:
                job.status = "failed"
                job.stage = "failed"
                job.error = str(exc)
                job.completed_at = _now()
                job.updated_at = _now()
                db.commit()
    return True
