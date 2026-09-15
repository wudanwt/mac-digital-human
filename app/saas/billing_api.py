from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import PaymentOrder, Plan, Subscription
from .security import Principal, get_principal, require_admin
from .services import active_subscription, audit, usage_summary
from .settings import saas_settings


router = APIRouter(prefix="/billing", tags=["billing"])


class OrderCreate(BaseModel):
    plan_code: str = Field(min_length=1, max_length=40)
    provider: str = Field(default="manual", pattern="^(manual|mock)$")


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
    }


def _order_dict(item: PaymentOrder) -> dict:
    return {
        "id": item.id,
        "plan_code": item.plan_code,
        "provider": item.provider,
        "external_id": item.external_id,
        "amount_cny": item.amount_cny,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "paid_at": item.paid_at.isoformat() if item.paid_at else None,
    }


def apply_paid_order(db: Session, order: PaymentOrder) -> Subscription:
    if order.status == "paid":
        return active_subscription(db, order.tenant_id)
    plan = db.get(Plan, order.plan_code)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=422, detail="Plan unavailable")
    now = datetime.now(timezone.utc)
    order.status = "paid"
    order.paid_at = now
    sub = active_subscription(db, order.tenant_id)
    sub.plan_code = plan.code
    sub.status = "active"
    sub.remaining_seconds = plan.monthly_minutes * 60
    sub.period_started_at = now
    sub.period_ends_at = now + timedelta(days=30)
    audit(
        db,
        action="billing.plan_activated",
        tenant_id=order.tenant_id,
        user_id=order.user_id,
        target_type="order",
        target_id=order.id,
        details={"plan": plan.code, "provider": order.provider},
    )
    return sub


@router.get("/plans")
def list_plans(db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    plans = db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_cny.asc())).all()
    return [_plan_dict(plan) for plan in plans]


@router.get("/subscription")
def get_subscription(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    sub = active_subscription(db, principal.tenant_id)
    summary = usage_summary(db, principal.tenant_id)
    summary.update(
        {
            "status": sub.status,
            "period_started_at": sub.period_started_at.isoformat(),
            "period_ends_at": sub.period_ends_at.isoformat() if sub.period_ends_at else None,
        }
    )
    db.commit()
    return summary


@router.post("/orders", status_code=201)
def create_order(
    body: OrderCreate,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    plan = db.get(Plan, body.plan_code)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")
    if body.provider == "mock" and saas_settings.is_production:
        raise HTTPException(status_code=400, detail="Mock payment is disabled in production")
    if body.provider not in saas_settings.payment_providers and body.provider != "mock":
        raise HTTPException(status_code=400, detail="Payment provider is not enabled")
    order = PaymentOrder(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        plan_code=plan.code,
        provider=body.provider,
        amount_cny=plan.price_cny,
    )
    db.add(order)
    db.flush()
    audit(
        db,
        action="billing.order_create",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="order",
        target_id=order.id,
        details={"plan": plan.code, "provider": body.provider},
    )
    if body.provider == "mock":
        apply_paid_order(db, order)
    db.commit()
    result = _order_dict(order)
    result["payment_state"] = "paid" if order.status == "paid" else "awaiting_admin_confirmation"
    if order.status != "paid":
        result["message"] = "Manual settlement requires platform administrator confirmation."
    return result


@router.get("/orders")
def list_orders(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    orders = db.scalars(
        select(PaymentOrder)
        .where(PaymentOrder.tenant_id == principal.tenant_id)
        .order_by(PaymentOrder.created_at.desc())
    ).all()
    return [_order_dict(item) for item in orders]
