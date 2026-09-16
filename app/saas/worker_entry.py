from __future__ import annotations

import json
import os
import platform
import socket
import threading
import time
from pathlib import Path

from sqlalchemy import select

from ..config import settings
from .background_themes import ensure_builtin_backgrounds
from .database import SessionLocal
from .models import Asset, Course
from .queue import build_job_queue, normalize_engine
from .settings import saas_settings
from .storage import object_store
from . import worker as base_worker


_OriginalMLXHandler = base_worker.LocalMLXCourseHandler


class BackgroundAwareMLXCourseHandler(_OriginalMLXHandler):
    """Adds SaaS background assets to the existing Apple-Silicon course renderer."""

    def _prepare_backgrounds(self, job) -> None:
        ensure_builtin_backgrounds()
        course_id = job.payload.get("course_id")
        if not course_id:
            return
        with SessionLocal() as db:
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
                expected_name = str(item.get("custom_bg") or f"asset-{asset.id}{suffix}")
                expected_name = Path(expected_name).name
                target = settings.workspace_dir / "backgrounds" / expected_name
                target.parent.mkdir(parents=True, exist_ok=True)
                object_store.materialize(asset.object_key, target)

    def render(self, job, progress=None):
        self._prepare_backgrounds(job)
        return super().render(job, progress=progress)


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
            }
            try:
                client.setex(key, 20, json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass
            time.sleep(5)

    threading.Thread(target=loop, name=f"worker-heartbeat-{engine}", daemon=True).start()


def run_forever() -> None:
    ensure_builtin_backgrounds()
    base_worker.LocalMLXCourseHandler = BackgroundAwareMLXCourseHandler
    engine = _renderer_engine()
    base_worker.job_queue = build_job_queue(engine=engine)
    _start_worker_heartbeat(engine)
    base_worker.run_forever()


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
