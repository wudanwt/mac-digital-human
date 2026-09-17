from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerNode(Base):
    __tablename__ = "worker_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120))
    credential_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="offline", index=True)
    accepting_tasks: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    slots_total: Mapped[int] = mapped_column(Integer, default=1)
    slots_busy: Mapped[int] = mapped_column(Integer, default=0)
    host: Mapped[str] = mapped_column(String(255), default="")
    platform: Mapped[str] = mapped_column(String(255), default="")
    machine: Mapped[str] = mapped_column(String(80), default="")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    versions_json: Mapped[str] = mapped_column(Text, default="{}")
    code_version: Mapped[str] = mapped_column(String(120), default="")
    model_version: Mapped[str] = mapped_column(String(120), default="")
    render_contract_version: Mapped[str] = mapped_column(String(120), default="")
    current_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    disk_free_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_available_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class RenderSubtask(Base):
    __tablename__ = "render_subtasks"
    __table_args__ = (
        UniqueConstraint("parent_job_id", "task_type", "slide_index", name="uq_render_subtask_parent_type_slide"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    parent_job_id: Mapped[str] = mapped_column(ForeignKey("render_jobs.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(24), index=True)
    # 0 is reserved for non-page tasks (prepare/finalize); page tasks use 1..N.
    slide_index: Mapped[int] = mapped_column(Integer, default=0)
    config_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="blocked", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True)
    estimated_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    assigned_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    active_attempt_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="blocked")
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class RenderAttempt(Base):
    __tablename__ = "render_attempts"
    __table_args__ = (
        UniqueConstraint("subtask_id", "attempt_no", name="uq_render_attempt_subtask_number"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    subtask_id: Mapped[str] = mapped_column(ForeignKey("render_subtasks.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str | None] = mapped_column(
        ForeignKey("worker_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    lease_token_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="claimed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RenderArtifact(Base):
    __tablename__ = "render_artifacts"
    __table_args__ = (
        UniqueConstraint("attempt_id", "kind", name="uq_render_artifact_attempt_kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    parent_job_id: Mapped[str] = mapped_column(ForeignKey("render_jobs.id", ondelete="CASCADE"), index=True)
    subtask_id: Mapped[str | None] = mapped_column(
        ForeignKey("render_subtasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("render_attempts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(60), index=True)
    slide_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    object_key: Mapped[str] = mapped_column(String(900), unique=True)
    content_type: Mapped[str] = mapped_column(String(160), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
