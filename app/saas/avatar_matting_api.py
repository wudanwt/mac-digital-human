from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .avatar_matting_service import matting_status_dict, queue_matting_job
from .database import get_db
from .models import Avatar
from .security import Principal, get_principal, require_admin
from .services import audit


router = APIRouter(prefix="/avatar-matting", tags=["avatar-matting"])


def _avatar(db: Session, principal: Principal, avatar_id: str) -> Avatar:
    item = db.scalar(select(Avatar).where(Avatar.id == avatar_id, Avatar.tenant_id == principal.tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Digital human not found")
    if not item.master_video_asset_id:
        raise HTTPException(status_code=422, detail="Digital human has no master video")
    return item


@router.get("")
def list_matting_statuses(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    avatars = db.scalars(
        select(Avatar).where(Avatar.tenant_id == principal.tenant_id).order_by(Avatar.created_at.desc())
    ).all()
    return [{"avatar_id": avatar.id, **matting_status_dict(db, avatar)} for avatar in avatars]


@router.get("/{avatar_id}")
def get_matting_status(
    avatar_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    avatar = _avatar(db, principal, avatar_id)
    return {"avatar_id": avatar.id, **matting_status_dict(db, avatar)}


@router.post("/{avatar_id}/ensure")
def ensure_matting_job(
    avatar_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    avatar = _avatar(db, principal, avatar_id)
    try:
        job = queue_matting_job(db, avatar, user_id=principal.user_id, force=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        action="avatar.matting.ensure",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="avatar",
        target_id=avatar.id,
        details={"job_id": job.id, "source_asset_id": avatar.master_video_asset_id, "model": job.model},
    )
    db.commit()
    return {"avatar_id": avatar.id, **matting_status_dict(db, avatar)}


@router.post("/{avatar_id}/rebuild")
def rebuild_matting_assets(
    avatar_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    avatar = _avatar(db, principal, avatar_id)
    try:
        job = queue_matting_job(db, avatar, user_id=principal.user_id, force=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        action="avatar.matting.rebuild",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type="avatar",
        target_id=avatar.id,
        details={"job_id": job.id, "source_asset_id": avatar.master_video_asset_id, "model": job.model},
    )
    db.commit()
    return {"avatar_id": avatar.id, **matting_status_dict(db, avatar)}
