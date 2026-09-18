from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AvatarMattingJob(Base):
    """Durable asset-level portrait matting job.

    This is intentionally separate from course render jobs: background removal is
    performed once when a digital-human master is prepared, then every course
    reuses the resulting alpha asset without running segmentation again.
    """

    __tablename__ = "avatar_matting_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    avatar_id: Mapped[str] = mapped_column(ForeignKey("avatars.id", ondelete="CASCADE"), index=True)
    source_asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    model: Mapped[str] = mapped_column(String(120), default="birefnet-portrait")
    alpha_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    poster_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    white_preview_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
