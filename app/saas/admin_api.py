from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .billing_api import apply_paid_order
from .database import get_db
from .models import AuditLog, PaymentOrder, RenderJobRecord, Subscription, Tenant, User
from .security import Principal, require_superuser
from .services import audit, grant_seconds


router = APIRouter(prefix="/admin", tags=["admin"])


class GrantCredits(BaseModel):
    tenant_id: str
    minutes: int = Field(ge=-100000, le=100000)
    reason: str = Field(default="admin_adjustment", max_length=240)


class UserStatusUpdate(BaseModel):
    is_active: bool


@router.get("/overview")
def overview(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    del principal
    return {
        "users": int(db.scalar(select(func.count()).select_from(User)) or 0),
        "tenants": int(db.scalar(select(func.count()).select_from(Tenant)) or 0),
        "queued_jobs": int(db.scalar(select(func.count()).select_from(RenderJobRecord).where(RenderJobRecord.status == "queued")) or 0),
        "running_jobs": int(db.scalar(select(func.count()).select_from(RenderJobRecord).where(RenderJobRecord.status == "running")) or 0),
        "failed_jobs": int(db.scalar(select(func.count()).select_from(RenderJobRecord).where(RenderJobRecord.status == "failed")) or 0),
        "pending_orders": int(db.scalar(select(func.count()).select_from(PaymentOrder).where(PaymentOrder.status == "pending")) or 0),
    }


@router.get("/users")
def users(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    del principal
    rows = db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
    return [
        {
            "id": item.id,
            "email": item.email,
            "display_name": item.display_name,
            "is_active": item.is_active,
            "is_superuser": item.is_superuser,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserStatusUpdate,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == principal.user_id and not body.is_active:
        raise HTTPException(status_code=400, detail="Cannot disable your own admin account")
    user.is_active = body.is_active
    audit(db, action="admin.user_status", user_id=principal.user_id, target_type="user", target_id=user.id, details={"is_active": body.is_active})
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.get("/tenants")
def tenants(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    del principal
    rows = db.scalars(select(Tenant).order_by(Tenant.created_at.desc()).limit(500)).all()
    result = []
    for item in rows:
        sub = db.scalar(select(Subscription).where(Subscription.tenant_id == item.id))
        result.append(
            {
                "id": item.id,
                "name": item.name,
                "slug": item.slug,
                "owner_user_id": item.owner_user_id,
                "plan_code": sub.plan_code if sub else None,
                "remaining_minutes": round((sub.remaining_seconds if sub else 0) / 60, 1),
                "created_at": item.created_at.isoformat(),
            }
        )
    return result


@router.post("/credits")
def grant_credits(
    body: GrantCredits,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    sub = grant_seconds(
        db,
        tenant_id=body.tenant_id,
        seconds=body.minutes * 60,
        actor_user_id=principal.user_id,
        reason=body.reason,
    )
    audit(db, action="admin.credit_grant", tenant_id=body.tenant_id, user_id=principal.user_id, target_type="subscription", target_id=sub.id, details={"minutes": body.minutes, "reason": body.reason})
    db.commit()
    return {"tenant_id": body.tenant_id, "remaining_minutes": round(sub.remaining_seconds / 60, 1)}


@router.get("/orders")
def orders(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    del principal
    rows = db.scalars(select(PaymentOrder).order_by(PaymentOrder.created_at.desc()).limit(500)).all()
    return [
        {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "user_id": item.user_id,
            "plan_code": item.plan_code,
            "provider": item.provider,
            "amount_cny": item.amount_cny,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


@router.post("/orders/{order_id}/mark-paid")
def mark_order_paid(
    order_id: str,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    order = db.get(PaymentOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    sub = apply_paid_order(db, order)
    audit(db, action="admin.order_paid", tenant_id=order.tenant_id, user_id=principal.user_id, target_type="order", target_id=order.id)
    db.commit()
    return {"order_id": order.id, "status": order.status, "plan_code": sub.plan_code, "remaining_minutes": round(sub.remaining_seconds / 60, 1)}


@router.get("/audit")
def audit_logs(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 200,
) -> list[dict]:
    del principal
    limit = max(1, min(limit, 1000))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "user_id": item.user_id,
            "action": item.action,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "details": json.loads(item.details_json or "{}"),
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]
