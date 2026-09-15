from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Asset,
    AuditLog,
    Avatar,
    Membership,
    Plan,
    Subscription,
    UsageLedger,
)
from .settings import saas_settings


def unique_slug(db: Session, name: str) -> str:
    from .models import Tenant

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    slug = base[:72]
    while db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        slug = f"{base[:60]}-{uuid4().hex[:8]}"
    return slug


def audit(
    db: Session,
    *,
    action: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    target_type: str = "",
    target_id: str = "",
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_subscription(db: Session, sub: Subscription) -> Subscription:
    now = utcnow()
    if sub.period_ends_at is None:
        sub.period_started_at = sub.period_started_at or now
        sub.period_ends_at = now + timedelta(days=30)
        return sub
    if sub.period_ends_at > now:
        return sub

    plan = db.get(Plan, sub.plan_code)
    if sub.plan_code == "free" and plan is not None and sub.status == "active":
        sub.remaining_seconds = plan.monthly_minutes * 60
        sub.period_started_at = now
        sub.period_ends_at = now + timedelta(days=30)
    elif sub.plan_code != "free":
        # Paid plans are one-period entitlements until a new paid order renews them.
        sub.status = "expired"
        sub.remaining_seconds = 0
    return sub


def active_subscription(db: Session, tenant_id: str, *, initial_seconds: int | None = None) -> Subscription:
    sub = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if sub is None:
        plan = db.get(Plan, "free")
        seconds = (plan.monthly_minutes if plan else saas_settings.free_plan_minutes) * 60
        status = "active"
        if initial_seconds is not None:
            seconds = max(0, int(initial_seconds))
            if seconds == 0:
                status = "inactive"
        now = utcnow()
        sub = Subscription(
            tenant_id=tenant_id,
            plan_code="free",
            status=status,
            remaining_seconds=seconds,
            period_started_at=now,
            period_ends_at=now + timedelta(days=30),
        )
        db.add(sub)
        db.flush()
    return _refresh_subscription(db, sub)


def plan_for_tenant(db: Session, tenant_id: str) -> Plan:
    sub = active_subscription(db, tenant_id)
    plan = db.get(Plan, sub.plan_code)
    if plan is None:
        raise HTTPException(status_code=500, detail="Tenant plan configuration is invalid")
    return plan


def enforce_storage_limit(db: Session, tenant_id: str, *, incoming_bytes: int = 0) -> None:
    plan = plan_for_tenant(db, tenant_id)
    used = int(
        db.scalar(select(func.coalesce(func.sum(Asset.size_bytes), 0)).where(Asset.tenant_id == tenant_id)) or 0
    )
    limit = max(0, plan.storage_gb) * 1024**3
    if used + max(0, int(incoming_bytes)) > limit:
        raise HTTPException(status_code=402, detail=f"Storage quota exceeded ({plan.storage_gb} GB plan limit)")


def enforce_avatar_limit(db: Session, tenant_id: str) -> None:
    plan = plan_for_tenant(db, tenant_id)
    count = int(db.scalar(select(func.count()).select_from(Avatar).where(Avatar.tenant_id == tenant_id)) or 0)
    if count >= plan.max_avatars:
        raise HTTPException(status_code=402, detail=f"Avatar limit reached ({plan.max_avatars})")


def enforce_member_limit(db: Session, tenant_id: str) -> None:
    plan = plan_for_tenant(db, tenant_id)
    count = int(db.scalar(select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant_id)) or 0)
    if count >= plan.max_members:
        raise HTTPException(status_code=402, detail=f"Workspace member limit reached ({plan.max_members})")


def estimate_script_seconds(script: list[dict] | None, *, fallback: int | None = None) -> int:
    fallback = max(1, int(fallback or saas_settings.default_render_estimate_seconds))
    if not script:
        return fallback
    total = 0.0
    usable = False
    for item in script:
        if not isinstance(item, dict):
            continue
        text = str(item.get("narration") or item.get("script") or "").strip()
        if not text:
            continue
        usable = True
        total += max(4.0, len(text) / 4.0)
    return max(fallback if not usable else 1, int(math.ceil(total)))


def _ledger_exists(db: Session, *, job_id: str, kind: str) -> bool:
    return bool(db.scalar(select(UsageLedger.id).where(UsageLedger.job_id == job_id, UsageLedger.kind == kind).limit(1)))


def reserve_render_seconds(db: Session, *, tenant_id: str, user_id: str, job_id: str, seconds: int) -> None:
    seconds = max(1, int(seconds))
    if _ledger_exists(db, job_id=job_id, kind="render_reserved_seconds"):
        return
    sub = active_subscription(db, tenant_id)
    if sub.status != "active":
        raise HTTPException(status_code=402, detail="Subscription is not active")
    if sub.remaining_seconds < seconds:
        raise HTTPException(status_code=402, detail="Insufficient render minutes")
    sub.remaining_seconds -= seconds
    db.add(UsageLedger(tenant_id=tenant_id, user_id=user_id, job_id=job_id, kind="render_reserved_seconds", units=float(seconds), details_json=json.dumps({"reserved": True})))


def refund_render_seconds(db: Session, *, tenant_id: str, user_id: str, job_id: str, seconds: int) -> None:
    if _ledger_exists(db, job_id=job_id, kind="render_refund_seconds"):
        return
    seconds = max(0, int(seconds))
    sub = active_subscription(db, tenant_id)
    sub.remaining_seconds += seconds
    db.add(UsageLedger(tenant_id=tenant_id, user_id=user_id, job_id=job_id, kind="render_refund_seconds", units=float(seconds), details_json=json.dumps({"refund": True})))


def reconcile_render_seconds(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    job_id: str,
    reserved_seconds: int,
    actual_seconds: float | None,
) -> int:
    if _ledger_exists(db, job_id=job_id, kind="render_settlement_seconds"):
        return 0
    actual = max(1, int(math.ceil(float(actual_seconds or reserved_seconds or 1))))
    reserved = max(1, int(reserved_seconds))
    delta = actual - reserved
    sub = active_subscription(db, tenant_id)
    if delta > 0:
        sub.remaining_seconds -= delta
    elif delta < 0:
        sub.remaining_seconds += -delta
    db.add(UsageLedger(tenant_id=tenant_id, user_id=user_id, job_id=job_id, kind="render_settlement_seconds", units=float(delta), details_json=json.dumps({"reserved": reserved, "actual": actual, "delta": delta})))
    return delta


def grant_seconds(
    db: Session,
    *,
    tenant_id: str,
    seconds: int,
    actor_user_id: str | None = None,
    reason: str = "manual_grant",
) -> Subscription:
    sub = active_subscription(db, tenant_id)
    sub.remaining_seconds += int(seconds)
    if seconds > 0 and sub.status == "inactive":
        sub.status = "active"
        sub.period_started_at = utcnow()
        sub.period_ends_at = sub.period_started_at + timedelta(days=30)
    db.add(UsageLedger(tenant_id=tenant_id, user_id=actor_user_id, kind="credit_grant_seconds", units=float(seconds), details_json=json.dumps({"reason": reason}, ensure_ascii=False)))
    return sub


def usage_summary(db: Session, tenant_id: str) -> dict:
    sub = active_subscription(db, tenant_id)
    plan = db.get(Plan, sub.plan_code)
    reserved = db.scalar(select(func.coalesce(func.sum(UsageLedger.units), 0.0)).where(UsageLedger.tenant_id == tenant_id, UsageLedger.kind == "render_reserved_seconds")) or 0.0
    settled = db.scalar(select(func.coalesce(func.sum(UsageLedger.units), 0.0)).where(UsageLedger.tenant_id == tenant_id, UsageLedger.kind == "render_settlement_seconds")) or 0.0
    refunded = db.scalar(select(func.coalesce(func.sum(UsageLedger.units), 0.0)).where(UsageLedger.tenant_id == tenant_id, UsageLedger.kind == "render_refund_seconds")) or 0.0
    consumed = float(reserved) + float(settled) - float(refunded)
    return {
        "plan_code": sub.plan_code,
        "plan_name": plan.name if plan else sub.plan_code,
        "status": sub.status,
        "remaining_seconds": sub.remaining_seconds,
        "remaining_minutes": round(sub.remaining_seconds / 60, 1),
        "consumed_seconds": consumed,
        "consumed_minutes": round(consumed / 60, 1),
        "storage_gb": plan.storage_gb if plan else 0,
        "max_avatars": plan.max_avatars if plan else 0,
        "max_members": plan.max_members if plan else 0,
    }


def ensure_membership(db: Session, *, tenant_id: str, user_id: str) -> Membership:
    membership = db.scalar(select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id))
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return membership
