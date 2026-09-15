from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Membership, Subscription, Tenant, User
from .security import Principal, create_access_token, get_principal, hash_password, require_owner, verify_password
from .services import active_subscription, audit, ensure_membership, unique_slug
from .settings import saas_settings


router = APIRouter(prefix="/auth", tags=["auth"])
workspace_router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)
    workspace_name: str = Field(default="我的工作区", min_length=1, max_length=160)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class MemberAdd(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(member|admin)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    workspace: dict


def _token_response(user: User, tenant: Tenant, membership: Membership) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user=user, tenant_id=tenant.id, role=membership.role),
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_superuser": user.is_superuser,
        },
        workspace={"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "role": membership.role},
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    email = body.email.lower().strip()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    try:
        password_hash = hash_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = User(
        email=email,
        password_hash=password_hash,
        display_name=body.display_name.strip() or email.split("@", 1)[0],
        is_superuser=email in {e.lower() for e in saas_settings.admin_emails},
    )
    db.add(user)
    db.flush()
    tenant = Tenant(name=body.workspace_name.strip(), slug=unique_slug(db, body.workspace_name), owner_user_id=user.id)
    db.add(tenant)
    db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db.add(membership)
    db.flush()
    sub = active_subscription(db, tenant.id)
    if sub.remaining_seconds <= 0:
        sub.remaining_seconds = saas_settings.free_plan_minutes * 60
    audit(db, action="auth.register", tenant_id=tenant.id, user_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return _token_response(user, tenant, membership)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at.asc()))
    if membership is None:
        raise HTTPException(status_code=403, detail="No workspace membership")
    tenant = db.get(Tenant, membership.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=500, detail="Workspace missing")
    audit(db, action="auth.login", tenant_id=tenant.id, user_id=user.id)
    db.commit()
    return _token_response(user, tenant, membership)


@router.get("/me")
def me(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.get(User, principal.user_id)
    tenant = db.get(Tenant, principal.tenant_id)
    memberships = db.scalars(select(Membership).where(Membership.user_id == principal.user_id)).all()
    workspace_ids = [m.tenant_id for m in memberships]
    tenants = db.scalars(select(Tenant).where(Tenant.id.in_(workspace_ids))).all() if workspace_ids else []
    roles = {m.tenant_id: m.role for m in memberships}
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_superuser": user.is_superuser,
        },
        "workspace": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "role": principal.role},
        "workspaces": [
            {"id": item.id, "name": item.name, "slug": item.slug, "role": roles[item.id]} for item in tenants
        ],
    }


@router.post("/switch-workspace/{tenant_id}", response_model=TokenResponse)
def switch_workspace(
    tenant_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    membership = ensure_membership(db, tenant_id=tenant_id, user_id=principal.user_id)
    user = db.get(User, principal.user_id)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _token_response(user, tenant, membership)


@workspace_router.get("")
def list_workspaces(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    memberships = db.scalars(select(Membership).where(Membership.user_id == principal.user_id)).all()
    result = []
    for membership in memberships:
        tenant = db.get(Tenant, membership.tenant_id)
        if tenant:
            result.append({"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "role": membership.role})
    return result


@workspace_router.post("", status_code=201)
def create_workspace(
    body: WorkspaceCreate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    tenant = Tenant(name=body.name.strip(), slug=unique_slug(db, body.name), owner_user_id=principal.user_id)
    db.add(tenant)
    db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=principal.user_id, role="owner")
    db.add(membership)
    active_subscription(db, tenant.id)
    audit(db, action="workspace.create", tenant_id=tenant.id, user_id=principal.user_id, target_type="tenant", target_id=tenant.id)
    db.commit()
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "role": membership.role}


@workspace_router.get("/members")
def list_members(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    rows = db.scalars(select(Membership).where(Membership.tenant_id == principal.tenant_id)).all()
    result = []
    for row in rows:
        user = db.get(User, row.user_id)
        if user:
            result.append({"id": user.id, "email": user.email, "display_name": user.display_name, "role": row.role})
    return result


@workspace_router.post("/members", status_code=201)
def add_member(
    body: MemberAdd,
    principal: Annotated[Principal, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None:
        raise HTTPException(status_code=404, detail="User must register before being added")
    existing = db.scalar(
        select(Membership).where(Membership.tenant_id == principal.tenant_id, Membership.user_id == user.id)
    )
    if existing:
        existing.role = body.role
        membership = existing
    else:
        membership = Membership(tenant_id=principal.tenant_id, user_id=user.id, role=body.role)
        db.add(membership)
    audit(
        db,
        action="workspace.member_upsert",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="user",
        target_id=user.id,
        details={"role": body.role},
    )
    db.commit()
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": membership.role}


@workspace_router.delete("/members/{user_id}", status_code=204)
def remove_member(
    user_id: str,
    principal: Annotated[Principal, Depends(require_owner)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    if user_id == principal.user_id:
        raise HTTPException(status_code=400, detail="Workspace owner cannot remove self")
    membership = db.scalar(
        select(Membership).where(Membership.tenant_id == principal.tenant_id, Membership.user_id == user_id)
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(membership)
    audit(db, action="workspace.member_remove", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="user", target_id=user_id)
    db.commit()
