from __future__ import annotations

from sqlalchemy import event, select, update
from sqlalchemy.engine import Connection

from .distributed_render_models import RenderSubtask
from .models import RenderJobRecord


_ACTIVE_PARENT = {"queued", "running"}


def _aggregate_parent_progress(connection: Connection, parent_job_id: str) -> None:
    task_table = RenderSubtask.__table__
    parent_table = RenderJobRecord.__table__
    rows = connection.execute(
        select(
            task_table.c.task_type,
            task_table.c.status,
            task_table.c.progress,
        ).where(task_table.c.parent_job_id == parent_job_id)
    ).mappings().all()
    if not rows:
        return

    prepare = next((row for row in rows if row["task_type"] == "prepare"), None)
    finalize = next((row for row in rows if row["task_type"] == "finalize"), None)
    pages = [row for row in rows if row["task_type"] == "page"]

    # Keep a little headroom for center preparation and finalization so the UI
    # never shows 100% until the published final asset and billing transaction
    # have both committed.
    prepare_value = max(0, min(100, int((prepare or {}).get("progress") or 0)))
    if not pages:
        value = int(prepare_value * 0.10)
    else:
        page_average = sum(max(0, min(100, int(row.get("progress") or 0))) for row in pages) / len(pages)
        value = 10 + int(page_average * 0.75)
        if all(row["status"] == "succeeded" for row in pages):
            finalize_value = max(0, min(100, int((finalize or {}).get("progress") or 0)))
            value = 85 + int(finalize_value * 0.14)
    value = max(0, min(99, value))

    parent = connection.execute(
        select(parent_table.c.status, parent_table.c.progress).where(parent_table.c.id == parent_job_id)
    ).mappings().first()
    if parent is None or parent["status"] not in _ACTIVE_PARENT:
        return
    current = int(parent.get("progress") or 0)
    # Progress is monotonic within a parent attempt. Individual page retries may
    # return to zero, but the parent UI must not jump backwards.
    if value <= current:
        return
    connection.execute(
        update(parent_table)
        .where(parent_table.c.id == parent_job_id, parent_table.c.status.in_(_ACTIVE_PARENT))
        .values(progress=value)
    )


@event.listens_for(RenderSubtask, "after_insert")
def _after_subtask_insert(_mapper, connection: Connection, target: RenderSubtask) -> None:
    _aggregate_parent_progress(connection, target.parent_job_id)


@event.listens_for(RenderSubtask, "after_update")
def _after_subtask_update(_mapper, connection: Connection, target: RenderSubtask) -> None:
    _aggregate_parent_progress(connection, target.parent_job_id)
