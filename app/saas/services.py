from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AuditLog, Membership, Plan, Subscription, UsageLedger


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


def active_subscription(db: Session, tenant_id: str) -> Subscription:
    sub = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if sub is None:
        plan = db.get(Plan, "free")
        seconds = (plan.monthly_minutes if plan else 30) * 60
        sub = Subscription(tenant_id=tenant_id, plan_code="free", remaining_seconds=seconds)
        db.add(sub)
        db.flush()
    return sub


def plan_for_tenant(db: Session, tenant_id: str) -> Plan:
    sub = active_subscription(db, tenant_id)
    plan = db.get(Plan, sub.plan_code)
    if plan is None:
        raise HTTPException(status_code=500, detail="Tenant plan configuration is invalid")
    return plan


def reserve_render_seconds(db: Session, *, tenant_id: str, user_id: str, job_id: str, seconds: int) -> None:
    seconds = max(1, int(seconds))
    sub = active_subscription(db, tenant_id)
    if sub.status != "active":
        raise HTTPException(status_code=402, detail="Subscription is not active")
    if sub.remaining_seconds < seconds:
        raise HTTPException(status_code=402, detail="Insufficient render minutes")
    sub.remaining_seconds -= seconds
    db.add(
        UsageLedger(
            tenant_id=tenant_id,
            user_id=user_id,
            job_id=job_id,
            kind="render_reserved_seconds",
            units=float(seconds),
            details_json=json.dumps({"reserved": True}),
        )
    )


def refund_render_seconds(db: Session, *, tenant_id: str, user_id: str, job_id: str, seconds: int) -> None:
    sub = active_subscription(db, tenant_id)
    sub.remaining_seconds += max(0, int(seconds))
    db.add(
        UsageLedger(
            tenant_id=tenant_id,
            user_id=user_id,
            job_id=job_id,
            kind="render_refund_seconds",
            units=float(seconds),
            details_json=json.dumps({"refund": True}),
        )
    )


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
    db.add(
        UsageLedger(
            tenant_id=tenant_id,
            user_id=actor_user_id,
            kind="credit_grant_seconds",
            units=float(seconds),
            details_json=json.dumps({"reason": reason}, ensure_ascii=False),
        )
    )
    return sub


def usage_summary(db: Session, tenant_id: str) -> dict:
    sub = active_subscription(db, tenant_id)
    plan = db.get(Plan, sub.plan_code)
    consumed = db.scalar(
        select(func.coalesce(func.sum(UsageLedger.units), 0.0)).where(
            UsageLedger.tenant_id == tenant_id,
            UsageLedger.kind == "render_reserved_seconds",
        )
    ) or 0.0
    refunded = db.scalar(
        select(func.coalesce(func.sum(UsageLedger.units), 0.0)).where(
            UsageLedger.tenant_id == tenant_id,
            UsageLedger.kind == "render_refund_seconds",
        )
    ) or 0.0
    return {
        "plan_code": sub.plan_code,
        "plan_name": plan.name if plan else sub.plan_code,
        "remaining_seconds": sub.remaining_seconds,
        "remaining_minutes": round(sub.remaining_seconds / 60, 1),
        "consumed_seconds": float(consumed) - float(refunded),
        "consumed_minutes": round((float(consumed) - float(refunded)) / 60, 1),
        "storage_gb": plan.storage_gb if plan else 0,
        "max_avatars": plan.max_avatars if plan else 0,
        "max_members": plan.max_members if plan else 0,
    }


def ensure_membership(db: Session, *, tenant_id: str, user_id: str) -> Membership:
    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return membership


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
