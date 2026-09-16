from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import Principal, get_principal, hash_password, verify_password
from .services import audit


router = APIRouter(prefix="/account", tags=["account"])


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("")
def get_account(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at.isoformat(),
    }


@router.patch("")
def update_account(
    body: ProfileUpdate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    user.display_name = body.display_name.strip()
    audit(
        db,
        action="account.profile_update",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_superuser": user.is_superuser,
    }


@router.post("/change-password", status_code=204)
def change_password(
    body: PasswordChange,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=422, detail="Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=422, detail="New password must be different")
    try:
        user.password_hash = hash_password(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        action="account.password_change",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
