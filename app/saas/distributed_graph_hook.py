from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.engine import Connection

from .distributed_render_models import RenderSubtask
from .models import RenderJobRecord
from .render_snapshot_models import RenderTaskSnapshot
from .settings import saas_settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: dict) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@event.listens_for(RenderJobRecord, "after_insert")
def _initialize_distributed_graph(_mapper, connection: Connection, target: RenderJobRecord) -> None:
    """Create the center-only prepare/finalize skeleton in the parent transaction.

    The snapshot capture listener is imported before this module in bootstrap, so
    the immutable snapshot row already exists when this listener runs.  Only
    MuseTalk jobs are diverted; mock and legacy jobs keep their existing queue.
    """

    if not saas_settings.distributed_render_enabled or target.engine != "musetalk":
        return
    snapshot_table = RenderTaskSnapshot.__table__
    snapshot = connection.execute(
        select(snapshot_table).where(snapshot_table.c.job_id == target.id)
    ).mappings().first()
    if snapshot is None:
        return

    task_table = RenderSubtask.__table__
    existing = connection.execute(
        select(task_table.c.task_type).where(task_table.c.parent_job_id == target.id)
    ).scalars().all()
    existing_types = set(existing)
    now = target.created_at or _now()
    try:
        payload = json.loads(target.payload_json or "{}")
    except Exception:
        payload = {}
    try:
        priority = int(payload.get("priority", 0)) if isinstance(payload, dict) else 0
    except (TypeError, ValueError):
        priority = 0

    if "prepare" not in existing_types:
        prepare_payload = {"task_type": "prepare", "snapshot_hash": snapshot["snapshot_hash"]}
        connection.execute(
            task_table.insert().values(
                id=uuid4().hex,
                tenant_id=target.tenant_id,
                parent_job_id=target.id,
                task_type="prepare",
                slide_index=0,
                config_hash=_hash(prepare_payload),
                payload_json=json.dumps(prepare_payload, ensure_ascii=False, sort_keys=True),
                status="queued",
                priority=priority,
                progress=0,
                stage="queued",
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    if "finalize" not in existing_types:
        finalize_payload = {"task_type": "finalize", "snapshot_hash": snapshot["snapshot_hash"]}
        connection.execute(
            task_table.insert().values(
                id=uuid4().hex,
                tenant_id=target.tenant_id,
                parent_job_id=target.id,
                task_type="finalize",
                slide_index=0,
                config_hash=_hash(finalize_payload),
                payload_json=json.dumps(finalize_payload, ensure_ascii=False, sort_keys=True),
                status="blocked",
                priority=priority,
                progress=0,
                stage="waiting_pages",
                blocked_reason="waiting for center prepare and page tasks",
                created_at=now,
                updated_at=now,
            )
        )
