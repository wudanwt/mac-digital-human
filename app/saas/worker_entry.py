from __future__ import annotations

import json
import logging
import os
import platform
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from ..config import settings
from . import worker as base_worker
from .avatar_alpha import AlphaCycleCache
from .avatar_matting_service import ready_matting_assets
from .avatar_matting_worker import process_one_avatar_matting, recover_stale_avatar_matting
from .background_themes import ensure_builtin_backgrounds
from .database import SessionLocal
from .models import Asset, Avatar, Course
from .queue import build_job_queue, normalize_engine
from .render_snapshot_service import load_snapshot_payload
from .settings import saas_settings
from .speech_preview_worker import process_one_speech_preview, recover_stale_speech_previews
from .storage import object_store
from .transparent_composer import TransparentCourseComposer


log = logging.getLogger("digital-human.saas.worker-entry")
_OriginalMLXHandler = base_worker.LocalMLXCourseHandler
_OriginalCourseComposer = base_worker.CourseComposer
_CONTEXT = threading.local()
_SLIDE_RE = re.compile(r"-slide-(\d+)$")


def _align_avatar_filter_graph(value: str) -> str:
    """Keep legacy/original avatar mode bottom-aligned like the browser preview."""
    if "[avatar]" not in value or "[1:v]scale=" not in value:
        return value
    return value.replace(
        ":(oh-ih)/2:color=black@0,fps=",
        ":oh-ih:color=black@0,fps=",
        1,
    )


class PreviewAlignedCourseComposer(_OriginalCourseComposer):
    @staticmethod
    def _run(cmd: list[str]) -> None:
        patched = [_align_avatar_filter_graph(item) if isinstance(item, str) else item for item in cmd]
        _OriginalCourseComposer._run(patched)


@dataclass
class CourseMatteContext:
    alpha_source: Path | None = None
    modes_by_slide: dict[int, str] = field(default_factory=dict)
    alpha_by_avatar_output: dict[str, Path] = field(default_factory=dict)
    mode_by_avatar_output: dict[str, str] = field(default_factory=dict)
    alpha_cache: AlphaCycleCache = field(default_factory=AlphaCycleCache)


def _ctx() -> CourseMatteContext | None:
    return getattr(_CONTEXT, "value", None)


def _snapshot_asset(db, job, snapshot: dict, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == job.tenant_id))
    if asset is None:
        raise RuntimeError(f"snapshot asset missing: {asset_id}")
    expected = ((snapshot.get("assets") or {}).get(asset.id) or {}).get("sha256")
    if expected and asset.sha256 and expected != asset.sha256:
        raise RuntimeError(f"snapshot asset hash changed: {asset.id}")
    return asset


class ContextualMatteMuseTalkEngine:
    """Wrap MuseTalk without changing its stable inference implementation."""

    def __init__(self, inner) -> None:
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def render(self, *args, **kwargs):
        result = self.inner.render(*args, **kwargs)
        context = _ctx()
        if context is None or context.alpha_source is None:
            return result
        job_id = str(kwargs.get("job_id") or "")
        match = _SLIDE_RE.search(job_id)
        slide_index = int(match.group(1)) if match else 0
        mode = context.modes_by_slide.get(slide_index, "original")
        if mode not in {"transparent", "white"}:
            return result
        avatar_output = Path(result.output)
        alpha_output = Path(result.workspace) / "avatar-alpha-cycle.mp4"
        context.alpha_cache.build_for_output(context.alpha_source, avatar_output, alpha_output)
        key = str(avatar_output.resolve())
        context.alpha_by_avatar_output[key] = alpha_output
        context.mode_by_avatar_output[key] = mode
        if isinstance(result.metadata, dict):
            result.metadata["avatar_mode"] = mode
            result.metadata["alpha_output"] = str(alpha_output)
        return result


class MatteAwareCourseComposer(PreviewAlignedCourseComposer):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.transparent_composer = TransparentCourseComposer(self.config)

    def compose_segment_layout(self, *args, **kwargs):
        avatar_video = kwargs.get("avatar_video")
        context = _ctx()
        if avatar_video is not None and context is not None:
            key = str(Path(avatar_video).resolve())
            mode = context.mode_by_avatar_output.get(key, "original")
            alpha = context.alpha_by_avatar_output.get(key)
            if mode in {"transparent", "white"}:
                return self.transparent_composer.compose_segment_layout(
                    *args,
                    **kwargs,
                    avatar_alpha_video=alpha,
                    avatar_mode=mode,
                )
        return super().compose_segment_layout(*args, **kwargs)


class BackgroundAwareMLXCourseHandler(_OriginalMLXHandler):
    """Adds backgrounds plus prepared alpha assets to the existing MLX renderer."""

    def __init__(self) -> None:
        super().__init__()
        self.avatar_engine = ContextualMatteMuseTalkEngine(self.avatar_engine)
        self.composer = MatteAwareCourseComposer(self.composer.config)

    def _prepare_backgrounds(self, job) -> None:
        ensure_builtin_backgrounds()
        with SessionLocal() as db:
            snapshot = load_snapshot_payload(db, job.id)
            if snapshot is not None:
                slides = ((snapshot.get("course") or {}).get("script")) or []
                for item in slides:
                    if not isinstance(item, dict):
                        continue
                    asset_id = item.get("background_asset_id")
                    if not asset_id:
                        continue
                    asset = _snapshot_asset(db, job, snapshot, str(asset_id))
                    if asset is None or asset.kind not in {"background", "image"}:
                        raise RuntimeError(f"background asset missing or invalid: {asset_id}")
                    suffix = Path(asset.name).suffix.lower() or ".png"
                    expected_name = Path(str(item.get("custom_bg") or f"asset-{asset.id}{suffix}")).name
                    target = settings.workspace_dir / "backgrounds" / expected_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    object_store.materialize(asset.object_key, target)
                return

            course_id = job.payload.get("course_id")
            if not course_id:
                return
            course = db.scalar(
                select(Course).where(Course.id == course_id, Course.tenant_id == job.tenant_id)
            )
            if course is None:
                return
            slides = json.loads(course.script_json or "[]")
            for item in slides:
                if not isinstance(item, dict):
                    continue
                asset_id = item.get("background_asset_id")
                if not asset_id:
                    continue
                asset = db.scalar(
                    select(Asset).where(
                        Asset.id == str(asset_id),
                        Asset.tenant_id == job.tenant_id,
                    )
                )
                if asset is None or asset.kind not in {"background", "image"}:
                    raise RuntimeError(f"background asset missing or invalid: {asset_id}")
                suffix = Path(asset.name).suffix.lower() or ".png"
                expected_name = Path(str(item.get("custom_bg") or f"asset-{asset.id}{suffix}")).name
                target = settings.workspace_dir / "backgrounds" / expected_name
                target.parent.mkdir(parents=True, exist_ok=True)
                object_store.materialize(asset.object_key, target)

    def _prepare_matte_context(self, job) -> CourseMatteContext:
        context = CourseMatteContext()
        with SessionLocal() as db:
            snapshot = load_snapshot_payload(db, job.id)
            if snapshot is not None:
                settings_payload = ((snapshot.get("course") or {}).get("settings")) or {}
                entries = [
                    item
                    for item in (((snapshot.get("course") or {}).get("script")) or [])
                    if isinstance(item, dict)
                ]
                global_mode = str(settings_payload.get("avatar_mode") or "original").strip().lower()
                for position, item in enumerate(entries, start=1):
                    index = int(item.get("index") or position)
                    mode = str(item.get("avatar_mode") or global_mode or "original").strip().lower()
                    if mode not in {"original", "transparent", "white"}:
                        mode = "original"
                    context.modes_by_slide[index] = mode
                needs_alpha = bool(snapshot.get("alpha_required")) or any(
                    mode in {"transparent", "white"} for mode in context.modes_by_slide.values()
                )
                if needs_alpha:
                    alpha_asset_id = str(snapshot.get("alpha_asset_id") or "") or None
                    if alpha_asset_id is None:
                        raise RuntimeError("课程选择了透明/白底讲师，但任务提交时透明资产尚未处理完成")
                    alpha_asset = _snapshot_asset(db, job, snapshot, alpha_asset_id)
                    if alpha_asset is None:
                        raise RuntimeError("任务快照中的透明资产不存在")
                    matte_dir = settings.workspace_dir / "saas-workers" / job.id / "matting"
                    matte_dir.mkdir(parents=True, exist_ok=True)
                    suffix = Path(alpha_asset.name).suffix.lower() or ".mp4"
                    context.alpha_source = object_store.materialize(
                        alpha_asset.object_key,
                        matte_dir / f"master-alpha{suffix}",
                    )
                return context

            course_id = job.payload.get("course_id")
            if not course_id:
                return context
            course = db.scalar(
                select(Course).where(Course.id == course_id, Course.tenant_id == job.tenant_id)
            )
            if course is None or not course.avatar_id:
                return context
            avatar = db.scalar(
                select(Avatar).where(Avatar.id == course.avatar_id, Avatar.tenant_id == job.tenant_id)
            )
            if avatar is None:
                return context
            alpha_asset, _, _, _ = ready_matting_assets(db, avatar)
            settings_payload = json.loads(course.settings_json or "{}")
            entries = [item for item in json.loads(course.script_json or "[]") if isinstance(item, dict)]
            global_mode = str(settings_payload.get("avatar_mode") or "original").strip().lower()
            for position, item in enumerate(entries, start=1):
                index = int(item.get("index") or position)
                mode = str(item.get("avatar_mode") or global_mode or "original").strip().lower()
                if mode not in {"original", "transparent", "white"}:
                    mode = "original"
                context.modes_by_slide[index] = mode
            needs_alpha = any(mode in {"transparent", "white"} for mode in context.modes_by_slide.values())
            if needs_alpha:
                if alpha_asset is None:
                    raise RuntimeError("课程选择了透明/白底讲师，但该数字人的透明资产尚未处理完成")
                matte_dir = settings.workspace_dir / "saas-workers" / job.id / "matting"
                matte_dir.mkdir(parents=True, exist_ok=True)
                suffix = Path(alpha_asset.name).suffix.lower() or ".mp4"
                context.alpha_source = object_store.materialize(
                    alpha_asset.object_key,
                    matte_dir / f"master-alpha{suffix}",
                )
        return context

    def render(self, job, progress=None):
        self._prepare_backgrounds(job)
        context = self._prepare_matte_context(job)
        _CONTEXT.value = context
        try:
            return super().render(job, progress=progress)
        finally:
            _CONTEXT.value = None


def _renderer_engine() -> str:
    renderer = os.getenv("SAAS_RENDERER", "mock")
    return normalize_engine(renderer)


def _start_worker_heartbeat(engine: str) -> None:
    if saas_settings.worker_backend != "redis":
        return
    try:
        import redis
    except ImportError:
        return

    client = redis.Redis.from_url(saas_settings.redis_url, decode_responses=True)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    key = f"{saas_settings.queue_name}:worker:{engine}:{worker_id}"

    def loop() -> None:
        while True:
            payload = {
                "worker_id": worker_id,
                "engine": engine,
                "host": socket.gethostname(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "pid": os.getpid(),
                "updated_at": time.time(),
                "capabilities": ["musetalk", "portrait-matting", "speech-preview", "transparent-avatar-compose"],
            }
            try:
                client.set(key, json.dumps(payload, ensure_ascii=False), ex=20)
            except Exception:
                pass
            time.sleep(5)

    threading.Thread(target=loop, name=f"worker-heartbeat-{engine}", daemon=True).start()


def run_forever() -> None:
    ensure_builtin_backgrounds()
    base_worker.LocalMLXCourseHandler = BackgroundAwareMLXCourseHandler
    base_worker.CourseComposer = MatteAwareCourseComposer
    engine = _renderer_engine()
    base_worker.job_queue = build_job_queue(engine=engine)
    _start_worker_heartbeat(engine)
    handler = base_worker.build_render_handler()
    recovered = base_worker.job_queue.recover_stale()
    recovered_previews = recover_stale_speech_previews() if engine == "musetalk" else 0
    recovered_matting = recover_stale_avatar_matting() if engine == "musetalk" else 0
    log.info(
        "Mac SaaS worker started renderer=%s recovered=%s speech_previews=%s avatar_matting=%s",
        handler.__class__.__name__,
        recovered,
        recovered_previews,
        recovered_matting,
    )
    last_recovery = time.monotonic()
    while True:
        # Run at most one job of each kind per cycle. Heavy local workloads stay
        # serialized, while repeated previews cannot starve a queued course.
        processed_preview = process_one_speech_preview() if engine == "musetalk" else False
        processed_matte = process_one_avatar_matting() if engine == "musetalk" else False
        processed_render = base_worker.process_one(handler)
        if time.monotonic() - last_recovery >= 60:
            recovered = base_worker.job_queue.recover_stale()
            if recovered:
                log.warning("Recovered %s stale course render jobs", recovered)
            if engine == "musetalk":
                recovered_matting = recover_stale_avatar_matting()
                if recovered_matting:
                    log.warning("Released %s stale avatar matting jobs", recovered_matting)
            last_recovery = time.monotonic()
        if not processed_preview and not processed_matte and not processed_render:
            time.sleep(0.2)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
