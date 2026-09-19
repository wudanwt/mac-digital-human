from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Plan(Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    monthly_minutes: Mapped[int] = mapped_column(Integer, default=0)
    storage_gb: Mapped[int] = mapped_column(Integer, default=5)
    max_avatars: Mapped[int] = mapped_column(Integer, default=1)
    max_members: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    price_cny: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), default="free")
    status: Mapped[str] = mapped_column(String(32), default="active")
    remaining_seconds: Mapped[int] = mapped_column(Integer, default=0)
    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    period_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(800), unique=True)
    uri: Mapped[str] = mapped_column(String(1200))
    content_type: Mapped[str] = mapped_column(String(160), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SystemAssetTemplate(Base):
    __tablename__ = "system_asset_templates"
    __table_args__ = (UniqueConstraint("kind", "source_id", name="uq_system_asset_template_source"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    metadata_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SystemAssetImport(Base):
    __tablename__ = "system_asset_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "template_id", name="uq_system_asset_import_tenant_template"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("system_asset_templates.id"), index=True)
    imported_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(60), default="cosyvoice")
    reference_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    image_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    master_video_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    ppt_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    avatar_id: Mapped[str | None] = mapped_column(ForeignKey("avatars.id"), nullable=True)
    voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    script_json: Mapped[str] = mapped_column(Text, default="[]")
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    output_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class RenderJobRecord(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(64), default="musetalk")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    output_uri: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    output_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_seconds: Mapped[int] = mapped_column(Integer, default=0)
    video_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_wait_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("render_jobs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    units: Mapped[float] = mapped_column(Float)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(40), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    consent_type: Mapped[str] = mapped_column(String(60), index=True)
    statement: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"))
    provider: Mapped[str] = mapped_column(String(40), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    amount_cny: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
