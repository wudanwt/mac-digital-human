from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RenderTaskSnapshot(Base):
    """Immutable inputs captured when a parent render job is submitted.

    The parent render job remains the billing/status record.  This row freezes the
    exact course inputs so later course edits cannot change an already queued job.
    It is intentionally one-to-one with ``render_jobs`` and is the foundation for
    the page-task scheduler introduced in the distributed rendering rollout.
    """

    __tablename__ = "render_task_snapshots"

    job_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("render_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
    )
    # Keep the original course id for audit/retry linkage, but do not make the
    # snapshot lifecycle depend on a mutable course row.
    course_id: Mapped[str] = mapped_column(String(32), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
