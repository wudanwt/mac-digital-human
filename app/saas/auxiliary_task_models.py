from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class AuxiliaryTaskLease(Base):
    __tablename__ = "auxiliary_task_leases"
    __table_args__ = (UniqueConstraint("kind", "job_id", name="uq_auxiliary_task_job"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str] = mapped_column(String(32), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("worker_nodes.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    artifacts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
