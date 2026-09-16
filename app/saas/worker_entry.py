from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from ..config import settings
from .background_themes import ensure_builtin_backgrounds
from .database import SessionLocal
from .models import Asset, Course
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
                # Never allow a course payload to escape the background workspace.
                expected_name = Path(expected_name).name
                target = settings.workspace_dir / "backgrounds" / expected_name
                target.parent.mkdir(parents=True, exist_ok=True)
                object_store.materialize(asset.object_key, target)

    def render(self, job, progress=None):
        self._prepare_backgrounds(job)
        return super().render(job, progress=progress)


def run_forever() -> None:
    ensure_builtin_backgrounds()
    base_worker.LocalMLXCourseHandler = BackgroundAwareMLXCourseHandler
    base_worker.run_forever()


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
