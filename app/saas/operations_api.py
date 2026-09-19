from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .billing_api import apply_paid_order
from .database import get_db
from .models import (
    Asset,
    AuditLog,
    Avatar,
    Course,
    Membership,
    PaymentOrder,
    Plan,
    RenderJobRecord,
    Subscription,
    Tenant,
    UsageLedger,
    User,
    VoiceProfile,
)
from .operations_models import SubscriptionPeriod
from .security import Principal, require_superuser
from .services import active_subscription, audit, grant_seconds, usage_summary


router = APIRouter(prefix="/admin/ops", tags=["admin-operations"])


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=80)
    monthly_minutes: int = Field(ge=0, le=100000)
    storage_gb: int = Field(ge=0, le=100000)
    max_avatars: int = Field(ge=0, le=10000)
    max_members: int = Field(ge=1, le=10000)
    priority: int = Field(ge=0, le=10000)
    price_cny: float = Field(ge=0, le=10000000)
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    monthly_minutes: int | None = Field(default=None, ge=0, le=100000)
    storage_gb: int | None = Field(default=None, ge=0, le=100000)
    max_avatars: int | None = Field(default=None, ge=0, le=10000)
    max_members: int | None = Field(default=None, ge=1, le=10000)
    priority: int | None = Field(default=None, ge=0, le=10000)
    price_cny: float | None = Field(default=None, ge=0, le=10000000)
    is_active: bool | None = None


class ActivatePlan(BaseModel):
    plan_code: str = Field(min_length=1, max_length=40)
    months: int = Field(default=1, ge=1, le=36)
    amount_cny: float | None = Field(default=None, ge=0, le=10000000)
    activation_mode: str = Field(default="replace", pattern="^(replace|renew)$")
    note: str = Field(default="", max_length=500)


class CreditAdjustment(BaseModel):
    minutes: int = Field(ge=-100000, le=100000)
    reason: str = Field(default="运营调整", min_length=1, max_length=240)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _plan_dict(plan: Plan) -> dict:
    return {
        "code": plan.code,
        "name": plan.name,
        "monthly_minutes": plan.monthly_minutes,
        "storage_gb": plan.storage_gb,
        "max_avatars": plan.max_avatars,
        "max_members": plan.max_members,
        "priority": plan.priority,
        "price_cny": plan.price_cny,
        "is_active": plan.is_active,
    }


def _period_dict(row: SubscriptionPeriod) -> dict:
    return {
        "id": row.id,
        "plan_code": row.plan_code,
        "source_order_id": row.source_order_id,
        "status": row.status,
        "activation_mode": row.activation_mode,
        "granted_minutes": round(row.granted_seconds / 60, 1),
        "amount_cny": row.amount_cny,
        "started_at": _iso(row.started_at),
        "ends_at": _iso(row.ends_at),
        "note": row.note,
        "created_by_user_id": row.created_by_user_id,
        "created_at": _iso(row.created_at),
    }


@router.get("/overview")
def operations_overview(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    del principal
    now = datetime.now(timezone.utc)
    seven_days = now + timedelta(days=7)
    current_period = or_(
        Subscription.plan_code == "free",
        Subscription.period_ends_at.is_(None),
        Subscription.period_ends_at > now,
    )
    paid_revenue = float(
        db.scalar(
            select(func.coalesce(func.sum(PaymentOrder.amount_cny), 0.0)).where(PaymentOrder.status == "paid")
        )
        or 0.0
    )
    rendered_seconds = float(
        db.scalar(
            select(func.coalesce(func.sum(RenderJobRecord.video_seconds), 0.0)).where(
                RenderJobRecord.status == "succeeded"
            )
        )
        or 0.0
    )
    return {
        "users": int(db.scalar(select(func.count()).select_from(User)) or 0),
        "customers": int(db.scalar(select(func.count()).select_from(Tenant)) or 0),
        "active_subscriptions": int(
            db.scalar(
                select(func.count()).select_from(Subscription).where(
                    Subscription.status == "active", current_period
                )
            ) or 0
        ),
        "paid_customers": int(
            db.scalar(
                select(func.count(func.distinct(Subscription.tenant_id))).where(
                    Subscription.status == "active",
                    Subscription.plan_code != "free",
                    Subscription.period_ends_at > now,
                )
            )
            or 0
        ),
        "pending_orders": int(
            db.scalar(select(func.count()).select_from(PaymentOrder).where(PaymentOrder.status == "pending")) or 0
        ),
        "paid_revenue_cny": round(paid_revenue, 2),
        "rendered_minutes": round(rendered_seconds / 60, 1),
        "expiring_7d": int(
            db.scalar(
                select(func.count()).select_from(Subscription).where(
                    Subscription.status == "active",
                    Subscription.plan_code != "free",
                    Subscription.period_ends_at.is_not(None),
                    Subscription.period_ends_at <= seven_days,
                    Subscription.period_ends_at >= now,
                )
            )
            or 0
        ),
    }


@router.get("/plans")
def list_all_plans(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    del principal
    return [_plan_dict(p) for p in db.scalars(select(Plan).order_by(Plan.price_cny.asc())).all()]


@router.post("/plans", status_code=201)
def create_plan(
    body: PlanCreate,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if db.get(Plan, body.code):
        raise HTTPException(status_code=409, detail="Plan code already exists")
    plan = Plan(**body.model_dump())
    db.add(plan)
    audit(
        db,
        action="admin.plan_create",
        user_id=principal.user_id,
        target_type="plan",
        target_id=plan.code,
        details=body.model_dump(),
    )
    db.commit()
    return _plan_dict(plan)


@router.patch("/plans/{plan_code}")
def update_plan(
    plan_code: str,
    body: PlanUpdate,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    plan = db.get(Plan, plan_code)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(plan, key, value)
    audit(
        db,
        action="admin.plan_update",
        user_id=principal.user_id,
        target_type="plan",
        target_id=plan.code,
        details=changes,
    )
    db.commit()
    return _plan_dict(plan)


@router.get("/customers")
def customers(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict]:
    del principal
    stmt = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = (
            select(Tenant)
            .join(User, User.id == Tenant.owner_user_id)
            .where(or_(Tenant.name.ilike(needle), Tenant.slug.ilike(needle), User.email.ilike(needle)))
            .order_by(Tenant.created_at.desc())
            .limit(limit)
        )
    rows = db.scalars(stmt).all()
    result: list[dict] = []
    for tenant in rows:
        owner = db.get(User, tenant.owner_user_id)
        sub = active_subscription(db, tenant.id)
        plan = db.get(Plan, sub.plan_code)
        result.append(
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "owner": {
                    "user_id": tenant.owner_user_id,
                    "email": owner.email if owner else "",
                    "display_name": owner.display_name if owner else "",
                },
                "plan_code": sub.plan_code,
                "plan_name": plan.name if plan else sub.plan_code,
                "subscription_status": sub.status,
                "remaining_minutes": round(sub.remaining_seconds / 60, 1),
                "period_ends_at": _iso(sub.period_ends_at),
                "created_at": _iso(tenant.created_at),
            }
        )
    db.commit()
    return result


@router.get("/customers/{tenant_id}")
def customer_detail(
    tenant_id: str,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    del principal
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Customer workspace not found")
    owner = db.get(User, tenant.owner_user_id)
    sub = active_subscription(db, tenant.id)
    plan = db.get(Plan, sub.plan_code)
    usage = usage_summary(db, tenant.id)
    storage_bytes = int(
        db.scalar(select(func.coalesce(func.sum(Asset.size_bytes), 0)).where(Asset.tenant_id == tenant.id)) or 0
    )
    periods = db.scalars(
        select(SubscriptionPeriod)
        .where(SubscriptionPeriod.tenant_id == tenant.id)
        .order_by(SubscriptionPeriod.created_at.desc())
        .limit(100)
    ).all()
    orders = db.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.tenant_id == tenant.id)
        .order_by(PaymentOrder.created_at.desc())
        .limit(100)
    ).all()
    ledger = db.scalars(
        select(UsageLedger)
        .where(UsageLedger.tenant_id == tenant.id)
        .order_by(UsageLedger.created_at.desc())
        .limit(100)
    ).all()
    audit_rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    db.commit()
    return {
        "customer": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "created_at": _iso(tenant.created_at),
            "owner": {
                "user_id": tenant.owner_user_id,
                "email": owner.email if owner else "",
                "display_name": owner.display_name if owner else "",
                "is_active": owner.is_active if owner else False,
            },
        },
        "subscription": {
            **usage,
            "plan_name": plan.name if plan else sub.plan_code,
            "period_started_at": _iso(sub.period_started_at),
            "period_ends_at": _iso(sub.period_ends_at),
        },
        "resources": {
            "avatars": int(db.scalar(select(func.count()).select_from(Avatar).where(Avatar.tenant_id == tenant.id)) or 0),
            "voices": int(db.scalar(select(func.count()).select_from(VoiceProfile).where(VoiceProfile.tenant_id == tenant.id)) or 0),
            "members": int(db.scalar(select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant.id)) or 0),
            "courses": int(db.scalar(select(func.count()).select_from(Course).where(Course.tenant_id == tenant.id)) or 0),
            "jobs": int(db.scalar(select(func.count()).select_from(RenderJobRecord).where(RenderJobRecord.tenant_id == tenant.id)) or 0),
            "storage_bytes": storage_bytes,
            "storage_gb_used": round(storage_bytes / 1024**3, 3),
        },
        "periods": [_period_dict(row) for row in periods],
        "orders": [
            {
                "id": row.id,
                "plan_code": row.plan_code,
                "provider": row.provider,
                "amount_cny": row.amount_cny,
                "status": row.status,
                "created_at": _iso(row.created_at),
                "paid_at": _iso(row.paid_at),
            }
            for row in orders
        ],
        "usage_ledger": [
            {
                "id": row.id,
                "kind": row.kind,
                "units": row.units,
                "details": json.loads(row.details_json or "{}"),
                "created_at": _iso(row.created_at),
            }
            for row in ledger
        ],
        "audit": [
            {
                "id": row.id,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "details": json.loads(row.details_json or "{}"),
                "created_at": _iso(row.created_at),
            }
            for row in audit_rows
        ],
    }


@router.post("/customers/{tenant_id}/activate", status_code=201)
def activate_customer_plan(
    tenant_id: str,
    body: ActivatePlan,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Customer workspace not found")
    plan = db.get(Plan, body.plan_code)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=422, detail="Plan unavailable")
    amount = body.amount_cny if body.amount_cny is not None else plan.price_cny * body.months
    order = PaymentOrder(
        tenant_id=tenant.id,
        user_id=tenant.owner_user_id,
        plan_code=plan.code,
        provider="manual",
        amount_cny=round(float(amount), 2),
    )
    db.add(order)
    db.flush()
    sub = apply_paid_order(
        db,
        order,
        months=body.months,
        activation_mode=body.activation_mode,
        actor_user_id=principal.user_id,
        note=body.note,
    )
    audit(
        db,
        action="admin.subscription_activate",
        tenant_id=tenant.id,
        user_id=principal.user_id,
        target_type="subscription",
        target_id=sub.id,
        details={
            "plan_code": plan.code,
            "months": body.months,
            "amount_cny": order.amount_cny,
            "activation_mode": body.activation_mode,
            "note": body.note,
        },
    )
    db.commit()
    return {
        "order_id": order.id,
        "status": order.status,
        "plan_code": sub.plan_code,
        "remaining_minutes": round(sub.remaining_seconds / 60, 1),
        "period_started_at": _iso(sub.period_started_at),
        "period_ends_at": _iso(sub.period_ends_at),
    }


@router.post("/customers/{tenant_id}/credits")
def adjust_customer_credits(
    tenant_id: str,
    body: CreditAdjustment,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Customer workspace not found")
    current = active_subscription(db, tenant_id)
    if current.status == "expired":
        raise HTTPException(status_code=422, detail="Activate a plan before adjusting an expired subscription")
    delta = body.minutes * 60
    if current.remaining_seconds + delta < 0:
        raise HTTPException(status_code=422, detail="Adjustment would make remaining credits negative")
    sub = grant_seconds(
        db,
        tenant_id=tenant_id,
        seconds=delta,
        actor_user_id=principal.user_id,
        reason=body.reason,
    )
    audit(
        db,
        action="admin.credit_adjust",
        tenant_id=tenant_id,
        user_id=principal.user_id,
        target_type="subscription",
        target_id=sub.id,
        details={"minutes": body.minutes, "reason": body.reason},
    )
    db.commit()
    return {
        "tenant_id": tenant_id,
        "remaining_minutes": round(sub.remaining_seconds / 60, 1),
    }
