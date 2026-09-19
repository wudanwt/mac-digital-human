from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_, select

from ..composer import CourseComposer, media_duration
from ..config import settings as app_settings
from .avatar_matting_service import queue_matting_job, ready_matting_assets
from .auxiliary_worker_api import reap_expired_auxiliary_leases
from .database import SessionLocal
from .distributed_render_models import RenderArtifact, RenderAttempt, RenderSubtask
from .distributed_scheduler import (
    publish_prepared_pages,
    reap_expired_page_leases,
    reap_stalled_page_attempts,
)
from .models import Asset, Avatar, Course, RenderJobRecord
from .render_core import PageRenderPlan, PageRenderResult, PreparedCourse, RenderWorkspace, finalize_course, prepare_course
from .render_snapshot_service import load_snapshot_payload
from .services import enforce_storage_limit, reconcile_render_seconds, refund_render_seconds
from .settings import saas_settings
from .storage import object_store
from .worker import _apply_ai_label

log = logging.getLogger("digital-human.saas.distributed-center")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
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


def _materialize(asset: Asset, destination: Path) -> Path:
    return object_store.materialize(asset.object_key, destination)


def _snapshot_asset(db, snapshot: dict[str, Any], asset_id: str | None, *, tenant_id: str) -> Asset | None:
    if not asset_id:
        return None
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id, Asset.status == "ready"))
    if asset is None:
        raise RuntimeError(f"snapshot asset unavailable: {asset_id}")
    expected = ((snapshot.get("assets") or {}).get(asset_id) or {}).get("sha256")
    if expected and asset.sha256 and expected != asset.sha256:
        raise RuntimeError(f"snapshot asset hash changed: {asset_id}")
    return asset


def _claim_center_task(task_type: str) -> str | None:
    now = _now()
    with SessionLocal() as db:
        task = db.scalar(
            select(RenderSubtask)
            .join(RenderJobRecord, RenderJobRecord.id == RenderSubtask.parent_job_id)
            .where(
                RenderSubtask.task_type == task_type,
                RenderSubtask.status.in_(["queued", "retry_wait"]),
                or_(RenderSubtask.available_at.is_(None), RenderSubtask.available_at <= now),
                RenderJobRecord.status.in_(["queued", "running"]),
            )
            .order_by(RenderSubtask.priority.desc(), RenderSubtask.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None
        task.status = "running"
        task.stage = "center_starting"
        task.progress = max(1, int(task.progress or 0))
        task.attempt_count = int(task.attempt_count or 0) + 1
        task.error = None
        if task.started_at is None:
            task.started_at = now
        parent = db.get(RenderJobRecord, task.parent_job_id)
        if parent is not None:
            parent.status = "running"
            parent.stage = "distributed_prepare" if task_type == "prepare" else "distributed_finalize"
            if parent.started_at is None:
                parent.started_at = now
        task_id = task.id
        db.commit()
        return task_id


def _retry_center_task(task_id: str, error: str, *, stage: str) -> None:
    with SessionLocal() as db:
        task = db.get(RenderSubtask, task_id)
        if task is None or task.status in {"succeeded", "canceled"}:
            return
        parent = db.get(RenderJobRecord, task.parent_job_id)
        attempts = int(task.attempt_count or 0)
        if attempts < max(1, saas_settings.distributed_max_attempts) and parent and parent.status in {"queued", "running"}:
            backoff = min(60, 5 * (2 ** max(0, attempts - 1)))
            task.status = "retry_wait"
            task.stage = "retry_wait"
            task.progress = 0
            task.error = error
            task.available_at = _now() + timedelta(seconds=backoff)
            db.commit()
            return
        task.status = "failed"
        task.stage = stage
        task.error = error
        task.completed_at = _now()
        if parent is not None and parent.status not in {"failed", "canceled", "succeeded"}:
            parent.status = "failed"
            parent.stage = stage
            parent.error = error
            parent.completed_at = _now()
            refund_render_seconds(
                db,
                tenant_id=parent.tenant_id,
                user_id=parent.user_id,
                job_id=parent.id,
                seconds=parent.estimated_seconds,
            )
            if parent.course_id:
                course = db.get(Course, parent.course_id)
                if course and course.status != "completed":
                    course.status = "draft"
        db.commit()


def _page_snapshot(snapshot: dict[str, Any], index: int) -> dict[str, Any]:
    for raw in snapshot.get("pages") or []:
        if isinstance(raw, dict) and int(raw.get("index") or 0) == index:
            return dict(raw)
    return {}


def _store_prepared_slide(
    *,
    db,
    task: RenderSubtask,
    slide_index: int,
    source: Path,
) -> RenderArtifact:
    existing = db.scalar(
        select(RenderArtifact)
        .where(
            RenderArtifact.parent_job_id == task.parent_job_id,
            RenderArtifact.subtask_id == task.id,
            RenderArtifact.kind == "prepared_slide",
            RenderArtifact.slide_index == slide_index,
            RenderArtifact.status == "ready",
        )
        .order_by(RenderArtifact.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return existing
    digest = _sha256(source)
    key = f"{task.tenant_id}/distributed/{task.parent_job_id}/prepared/slide-{slide_index:04d}-{digest[:12]}.png"
    object_store.put_file(source, key)
    artifact = RenderArtifact(
        tenant_id=task.tenant_id,
        parent_job_id=task.parent_job_id,
        subtask_id=task.id,
        attempt_id=None,
        kind="prepared_slide",
        slide_index=slide_index,
        object_key=key,
        content_type="image/png",
        size_bytes=source.stat().st_size,
        sha256=digest,
        status="ready",
        metadata_json=json.dumps({"source": "ppt_prepare"}, ensure_ascii=False),
        expires_at=_now() + timedelta(days=7),
    )
    db.add(artifact)
    db.flush()
    return artifact


def _resolve_alpha_or_block(task_id: str, snapshot: dict[str, Any]) -> str | None:
    if not snapshot.get("alpha_required"):
        return None
    frozen = str(snapshot.get("alpha_asset_id") or "") or None
    if frozen:
        return frozen
    avatar_id = str((snapshot.get("avatar") or {}).get("id") or "")
    if not avatar_id:
        raise RuntimeError("transparent page has no frozen avatar id")
    with SessionLocal() as db:
        task = db.get(RenderSubtask, task_id)
        if task is None:
            raise RuntimeError("prepare task disappeared")
        parent = db.get(RenderJobRecord, task.parent_job_id)
        avatar = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == task.tenant_id))
        if avatar is None:
            raise RuntimeError("transparent page avatar no longer exists")
        alpha, _, _, job = ready_matting_assets(db, avatar)
        if alpha is not None:
            return alpha.id
        if job is None or job.status not in {"queued", "running"}:
            queue_matting_job(db, avatar, user_id=parent.user_id if parent else "", force=False)
        task.status = "blocked"
        task.stage = "waiting_matting"
        task.blocked_reason = "waiting for transparent avatar asset"
        task.available_at = None
        if parent and parent.status in {"queued", "running"}:
            parent.status = "running"
            parent.stage = "waiting_avatar_matting"
        db.commit()
    return None


def _wake_waiting_matting() -> int:
    woke = 0
    with SessionLocal() as db:
        tasks = db.scalars(
            select(RenderSubtask).where(
                RenderSubtask.task_type == "prepare",
                RenderSubtask.status == "blocked",
                RenderSubtask.stage == "waiting_matting",
            )
        ).all()
        for task in tasks:
            snapshot = load_snapshot_payload(db, task.parent_job_id)
            if not snapshot:
                continue
            avatar_id = str((snapshot.get("avatar") or {}).get("id") or "")
            avatar = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == task.tenant_id)) if avatar_id else None
            if avatar is None:
                continue
            alpha, _, _, job = ready_matting_assets(db, avatar)
            if alpha is not None:
                task.status = "queued"
                task.stage = "queued"
                task.blocked_reason = None
                task.available_at = _now()
                woke += 1
            elif job is not None and job.status == "failed":
                # Let prepare run again so the normal retry/failure policy can
                # record a useful diagnostic instead of leaving the parent stuck.
                task.status = "queued"
                task.stage = "queued"
                task.blocked_reason = None
                task.available_at = _now()
                woke += 1
        if woke:
            db.commit()
    return woke


def process_prepare(task_id: str) -> bool:
    work = app_settings.workspace_dir / "distributed-center" / task_id
    workspace = RenderWorkspace.create(work)
    try:
        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            if task is None or task.status != "running":
                return False
            parent = db.get(RenderJobRecord, task.parent_job_id)
            snapshot = load_snapshot_payload(db, task.parent_job_id)
            if parent is None or snapshot is None:
                raise RuntimeError("parent render snapshot is missing")
            if parent.status == "canceled":
                task.status = "canceled"
                task.stage = "canceled"
                task.completed_at = _now()
                db.commit()
                return True
            ppt = _snapshot_asset(db, snapshot, snapshot.get("ppt_asset_id"), tenant_id=task.tenant_id)
            if ppt is None:
                raise RuntimeError("frozen PPT asset is missing")
            ppt_path = _materialize(ppt, work / "assets" / f"ppt{Path(ppt.name).suffix or '.pptx'}")
            script = [dict(item) for item in ((snapshot.get("course") or {}).get("script") or []) if isinstance(item, dict)]
            course_settings = dict((snapshot.get("course") or {}).get("settings") or {})
            task.progress = 10
            task.stage = "ppt_prepare"
            db.commit()

        alpha_asset_id = _resolve_alpha_or_block(task_id, snapshot)
        if snapshot.get("alpha_required") and not alpha_asset_id:
            return True

        prepared = prepare_course(
            ppt_path=ppt_path,
            workspace=workspace,
            script_entries=script,
            settings_payload=course_settings,
        )

        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            parent = db.get(RenderJobRecord, task.parent_job_id) if task else None
            if task is None or parent is None or task.status != "running":
                return False
            if parent.status == "canceled":
                task.status = "canceled"
                task.stage = "canceled"
                task.completed_at = _now()
                db.commit()
                return True
            task.progress = 55
            task.stage = "publishing_pages"
            db.flush()

            page_payloads: list[dict[str, Any]] = []
            slide_manifest: dict[str, Any] = {}
            for plan in prepared.plans:
                slide_path = workspace.slide_dir / f"slide-{plan.index}.png"
                if not slide_path.exists():
                    alternatives = sorted(workspace.slide_dir.glob(f"*{plan.index}*.png"))
                    if not alternatives:
                        raise RuntimeError(f"prepared slide image missing: {plan.index}")
                    slide_path = alternatives[0]
                slide_artifact = _store_prepared_slide(db=db, task=task, slide_index=plan.index, source=slide_path)
                frozen_page = _page_snapshot(snapshot, plan.index)
                explicit_audio = frozen_page.get("explicit_audio_asset_id")
                preview_audio = frozen_page.get("preview_audio_asset_id")
                direct_audio = snapshot.get("direct_audio_asset_id") if len(prepared.plans) == 1 else None
                fixed_audio = explicit_audio or preview_audio or direct_audio
                if explicit_audio:
                    audio_source = "explicit"
                elif preview_audio:
                    audio_source = "speech_preview"
                elif direct_audio:
                    audio_source = "direct"
                else:
                    audio_source = "synthesized"
                avatar_mode = str(frozen_page.get("avatar_mode") or course_settings.get("avatar_mode") or "original").lower()
                page_payload = {
                    "index": plan.index,
                    "title": plan.title,
                    "narration": plan.narration,
                    "layout": plan.layout,
                    "override": plan.override,
                    "course_settings": course_settings,
                    "voice": snapshot.get("voice"),
                    "master_video_asset_id": (snapshot.get("avatar") or {}).get("master_video_asset_id"),
                    "reference_audio_asset_id": (snapshot.get("voice") or {}).get("reference_asset_id") if snapshot.get("voice") else None,
                    "alpha_asset_id": alpha_asset_id if avatar_mode in {"transparent", "white"} else None,
                    "avatar_mode": avatar_mode,
                    "audio_asset_id": fixed_audio,
                    "audio_source": audio_source,
                    "background_asset_id": frozen_page.get("background_asset_id"),
                    "slide_artifact_id": slide_artifact.id,
                    "render_contract_version": saas_settings.render_contract_version,
                    "estimated_seconds": max(4.0, len(plan.narration) / 4.0),
                }
                page_payloads.append(page_payload)
                slide_manifest[str(plan.index)] = {
                    "artifact_id": slide_artifact.id,
                    "sha256": slide_artifact.sha256,
                    "size_bytes": slide_artifact.size_bytes,
                }

            publish_prepared_pages(
                db,
                parent_job_id=parent.id,
                pages=page_payloads,
                prepared_manifest={
                    "render_contract_version": saas_settings.render_contract_version,
                    "slides": slide_manifest,
                    "alpha_asset_id": alpha_asset_id,
                },
            )
            task.progress = 100
            db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        log.exception("Center prepare failed task=%s", task_id)
        _retry_center_task(task_id, str(exc), stage="prepare_failed")
        return True


def _probe_video(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed: {path}")
    data = json.loads(proc.stdout or "{}")
    video = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
    audio = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), {})
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": video.get("avg_frame_rate") or video.get("r_frame_rate") or "",
        "pix_fmt": video.get("pix_fmt") or "",
        "video_codec": video.get("codec_name") or "",
        "audio_codec": audio.get("codec_name") or "",
        "audio_sample_rate": int(audio.get("sample_rate") or 0) if str(audio.get("sample_rate") or "").isdigit() else 0,
        "audio_channels": int(audio.get("channels") or 0),
        "duration": float((data.get("format") or {}).get("duration") or 0.0),
    }


def _successful_page_artifacts(db, task: RenderSubtask) -> tuple[RenderArtifact, RenderArtifact, dict[str, Any]]:
    attempt = db.scalar(
        select(RenderAttempt)
        .where(RenderAttempt.subtask_id == task.id, RenderAttempt.status == "succeeded")
        .order_by(RenderAttempt.attempt_no.desc())
        .limit(1)
    )
    if attempt is None:
        raise RuntimeError(f"successful attempt missing for page {task.slide_index}")
    artifacts = db.scalars(
        select(RenderArtifact).where(RenderArtifact.attempt_id == attempt.id, RenderArtifact.status == "ready")
    ).all()
    by_kind = {item.kind: item for item in artifacts}
    if "page_video" not in by_kind or "page_audio" not in by_kind:
        raise RuntimeError(f"page artifacts incomplete for page {task.slide_index}")
    metrics = _json(attempt.metrics_json, {})
    return by_kind["page_video"], by_kind["page_audio"], metrics if isinstance(metrics, dict) else {}


def _validate_contract(probes: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    if not probes:
        raise RuntimeError("no page segments available for finalize")
    keys = ("width", "height", "fps", "pix_fmt", "video_codec", "audio_codec", "audio_sample_rate", "audio_channels")
    baseline = {key: probes[0][1].get(key) for key in keys}
    for index, probe in probes[1:]:
        current = {key: probe.get(key) for key in keys}
        if current != baseline:
            raise RuntimeError(f"page encoding contract mismatch at page {index}: {current} != {baseline}")
    return baseline


def process_finalize(task_id: str) -> bool:
    work = app_settings.workspace_dir / "distributed-center" / task_id / "finalize"
    workspace = RenderWorkspace.create(work)
    output_key: str | None = None
    try:
        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            if task is None or task.status != "running":
                return False
            parent = db.get(RenderJobRecord, task.parent_job_id)
            snapshot = load_snapshot_payload(db, task.parent_job_id)
            if parent is None or snapshot is None:
                raise RuntimeError("parent render snapshot is missing")
            if parent.status == "canceled":
                task.status = "canceled"
                task.stage = "canceled"
                task.completed_at = _now()
                db.commit()
                return True
            pages = db.scalars(
                select(RenderSubtask)
                .where(
                    RenderSubtask.parent_job_id == parent.id,
                    RenderSubtask.task_type == "page",
                )
                .order_by(RenderSubtask.slide_index.asc())
            ).all()
            if not pages or any(item.status != "succeeded" for item in pages):
                raise RuntimeError("finalize started before all page tasks succeeded")
            task.progress = 10
            task.stage = "materializing_pages"
            db.commit()

        results: list[PageRenderResult] = []
        plans: list[PageRenderPlan] = []
        probes: list[tuple[int, dict[str, Any]]] = []
        with SessionLocal() as db:
            pages = db.scalars(
                select(RenderSubtask)
                .where(RenderSubtask.parent_job_id == task.parent_job_id, RenderSubtask.task_type == "page")
                .order_by(RenderSubtask.slide_index.asc())
            ).all()
            for page in pages:
                payload = _json(page.payload_json, {})
                if not isinstance(payload, dict):
                    raise RuntimeError(f"page payload invalid: {page.slide_index}")
                video_artifact, audio_artifact, metrics = _successful_page_artifacts(db, page)
                video_path = object_store.materialize(
                    video_artifact.object_key,
                    workspace.segment_dir / f"{page.slide_index:03d}.mp4",
                )
                audio_path = object_store.materialize(
                    audio_artifact.object_key,
                    workspace.audio_dir / f"{page.slide_index:03d}.wav",
                )
                if _sha256(video_path) != video_artifact.sha256 or _sha256(audio_path) != audio_artifact.sha256:
                    raise RuntimeError(f"artifact hash validation failed for page {page.slide_index}")
                probe = _probe_video(video_path)
                probes.append((page.slide_index, probe))
                audio_seconds = media_duration(audio_path)
                results.append(
                    PageRenderResult(
                        index=page.slide_index,
                        segment_path=video_path,
                        audio_path=audio_path,
                        audio_seconds=audio_seconds,
                        audio_source=str(metrics.get("audio_source") or payload.get("audio_source") or "unknown"),
                        tts_elapsed_seconds=float(metrics.get("tts_elapsed_seconds") or 0.0),
                        render_seconds=float(metrics["render_seconds"]) if metrics.get("render_seconds") is not None else None,
                        metadata=metrics,
                    )
                )
                override = dict(payload.get("override") or {})
                plans.append(
                    PageRenderPlan(
                        index=page.slide_index,
                        title=str(payload.get("title") or ""),
                        narration=str(payload.get("narration") or ""),
                        layout=str(payload.get("layout") or "pip"),
                        override=override,
                        slide=SimpleNamespace(index=page.slide_index),
                    )
                )

        encoding_contract = _validate_contract(probes)
        settings_payload = dict((snapshot.get("course") or {}).get("settings") or {})
        prepared = PreparedCourse(
            workspace=workspace,
            deck=None,
            plans=tuple(plans),
            settings_payload=settings_payload,
        )
        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            if task is not None:
                task.progress = 55
                task.stage = "concat"
                task.payload_json = json.dumps(
                    {**_json(task.payload_json, {}), "encoding_contract": encoding_contract},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                db.commit()

        composer = CourseComposer()
        output = finalize_course(prepared=prepared, results=results, composer=composer)
        labeled = _apply_ai_label(output)
        duration = media_duration(labeled)
        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            parent = db.get(RenderJobRecord, task.parent_job_id) if task else None
            if task is None or parent is None:
                raise RuntimeError("parent disappeared before publish")
            if parent.status == "canceled":
                task.status = "canceled"
                task.stage = "canceled"
                task.completed_at = _now()
                db.commit()
                return True
            enforce_storage_limit(db, parent.tenant_id, incoming_bytes=labeled.stat().st_size)
            task.progress = 85
            task.stage = "publishing"
            db.commit()

        output_key = f"{parent.tenant_id}/outputs/{parent.id}/result.mp4"
        uri = object_store.put_file(labeled, output_key)
        with SessionLocal() as db:
            task = db.get(RenderSubtask, task_id)
            parent = db.get(RenderJobRecord, task.parent_job_id) if task else None
            if task is None or parent is None:
                object_store.delete(output_key)
                raise RuntimeError("parent disappeared after publish")
            if parent.status == "canceled":
                object_store.delete(output_key)
                task.status = "canceled"
                task.stage = "canceled"
                task.completed_at = _now()
                db.commit()
                return True
            existing_asset = db.get(Asset, parent.output_asset_id) if parent.output_asset_id else None
            if existing_asset is None:
                asset = Asset(
                    tenant_id=parent.tenant_id,
                    user_id=parent.user_id,
                    kind="output",
                    name=f"{parent.course_id or parent.id}.mp4",
                    object_key=output_key,
                    uri=uri,
                    content_type="video/mp4",
                    size_bytes=labeled.stat().st_size,
                    sha256=_sha256(labeled),
                    status="ready",
                )
                db.add(asset)
                db.flush()
            else:
                asset = existing_asset

            task.status = "succeeded"
            task.progress = 100
            task.stage = "completed"
            task.error = None
            task.completed_at = _now()
            parent.status = "succeeded"
            parent.progress = 100
            parent.stage = "completed"
            parent.output_uri = uri
            parent.output_asset_id = asset.id
            parent.video_seconds = duration
            parent.completed_at = _now()
            reconcile_render_seconds(
                db,
                tenant_id=parent.tenant_id,
                user_id=parent.user_id,
                job_id=parent.id,
                reserved_seconds=parent.estimated_seconds,
                actual_seconds=duration,
            )
            if parent.course_id:
                course = db.get(Course, parent.course_id)
                if course and course.tenant_id == parent.tenant_id:
                    course.status = "completed"
                    course.output_asset_id = asset.id
            db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        log.exception("Center finalize failed task=%s", task_id)
        if output_key:
            try:
                object_store.delete(output_key)
            except Exception:
                pass
        _retry_center_task(task_id, str(exc), stage="finalize_failed")
        return True


def _recover_stale_center_tasks() -> int:
    cutoff = _now() - timedelta(seconds=max(60, saas_settings.distributed_stall_seconds))
    recovered = 0
    with SessionLocal() as db:
        tasks = db.scalars(
            select(RenderSubtask)
            .where(
                RenderSubtask.task_type.in_(["prepare", "finalize"]),
                RenderSubtask.status == "running",
                RenderSubtask.updated_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for task in tasks:
            task.status = "retry_wait"
            task.stage = "retry_wait"
            task.error = "center executor stalled or restarted"
            task.available_at = _now() + timedelta(seconds=5)
            recovered += 1
        if recovered:
            db.commit()
    return recovered


def run_forever() -> None:
    if not saas_settings.distributed_render_enabled:
        raise RuntimeError("Set SAAS_DISTRIBUTED_RENDER_ENABLED=true before starting the center executor")
    log.info("Distributed center executor started")
    last_reap = 0.0
    while True:
        processed = False
        prepare_id = _claim_center_task("prepare")
        if prepare_id:
            processed = process_prepare(prepare_id) or processed
        finalize_id = _claim_center_task("finalize")
        if finalize_id:
            processed = process_finalize(finalize_id) or processed
        now = time.monotonic()
        if now - last_reap >= max(5, saas_settings.distributed_reaper_seconds):
            with SessionLocal() as db:
                recovered = reap_expired_page_leases(db)
                stalled = reap_stalled_page_attempts(db)
                auxiliary_recovered = reap_expired_auxiliary_leases(db)
                if recovered or stalled or auxiliary_recovered:
                    db.commit()
                if recovered:
                    log.warning("Recovered %s expired page leases", recovered)
                if stalled:
                    log.warning("Recovered %s stalled page attempts", stalled)
                if auxiliary_recovered:
                    log.warning("Recovered %s expired auxiliary task leases", auxiliary_recovered)
            woke = _wake_waiting_matting()
            if woke:
                log.info("Requeued %s prepare tasks after matting became ready", woke)
            stale = _recover_stale_center_tasks()
            if stale:
                log.warning("Recovered %s stale center tasks", stale)
            last_reap = now
        if not processed:
            time.sleep(0.5)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_forever()


if __name__ == "__main__":
    main()
