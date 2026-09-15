from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Asset, Avatar, Course, VoiceProfile
from .security import Principal, get_principal, require_admin
from .services import audit, enforce_storage_limit
from .settings import saas_settings
from .storage import object_store


router = APIRouter(prefix="/assets", tags=["assets"])

ALLOWED_KINDS = {"ppt", "document", "image", "video", "audio", "background", "output", "other"}
ALLOWED_EXTENSIONS = {
    ".pptx", ".ppt", ".pdf", ".png", ".jpg", ".jpeg", ".webp",
    ".mp4", ".mov", ".m4v", ".wav", ".mp3", ".m4a", ".aac", ".flac",
}


def _serialize(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "kind": asset.kind,
        "name": asset.name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "status": asset.status,
        "created_at": asset.created_at.isoformat(),
        "download_url": f"{saas_settings.api_prefix}/assets/{asset.id}/download",
    }


def _owned_asset(db: Session, tenant_id: str, asset_id: str) -> Asset:
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def _assert_not_referenced(db: Session, asset: Asset) -> None:
    tenant_id = asset.tenant_id
    if db.scalar(
        select(Avatar.id).where(
            Avatar.tenant_id == tenant_id,
            or_(Avatar.image_asset_id == asset.id, Avatar.master_video_asset_id == asset.id),
        ).limit(1)
    ):
        raise HTTPException(status_code=409, detail="Asset is referenced by an avatar")
    if db.scalar(
        select(VoiceProfile.id).where(
            VoiceProfile.tenant_id == tenant_id,
            VoiceProfile.reference_asset_id == asset.id,
        ).limit(1)
    ):
        raise HTTPException(status_code=409, detail="Asset is referenced by a voice profile")
    if db.scalar(
        select(Course.id).where(
            Course.tenant_id == tenant_id,
            or_(Course.ppt_asset_id == asset.id, Course.output_asset_id == asset.id),
        ).limit(1)
    ):
        raise HTTPException(status_code=409, detail="Asset is referenced by a course")


@router.get("")
def list_assets(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    kind: str | None = None,
) -> list[dict]:
    stmt = select(Asset).where(Asset.tenant_id == principal.tenant_id)
    if kind:
        stmt = stmt.where(Asset.kind == kind)
    assets = db.scalars(stmt.order_by(Asset.created_at.desc())).all()
    return [_serialize(asset) for asset in assets]


@router.post("", status_code=201)
def upload_asset(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    kind: str = Form("other"),
) -> dict:
    kind = kind.lower().strip()
    if kind not in ALLOWED_KINDS or kind == "output":
        raise HTTPException(status_code=422, detail="Unsupported asset kind")
    original = Path(file.filename or "upload.bin").name
    ext = Path(original).suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file extension: {ext}")

    max_bytes = saas_settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    suffix = ext or ".bin"
    fd, temp_name = tempfile.mkstemp(prefix="saas-upload-", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)
    object_key = ""
    try:
        with temp_path.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds {saas_settings.max_upload_mb} MB limit")
                digest.update(chunk)
                out.write(chunk)
        enforce_storage_limit(db, principal.tenant_id, incoming_bytes=size)
        object_key = f"{principal.tenant_id}/{kind}/{uuid4().hex}{suffix}"
        uri = object_store.put_file(temp_path, object_key)
        asset = Asset(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            kind=kind,
            name=original,
            object_key=object_key,
            uri=uri,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
        db.add(asset)
        db.flush()
        audit(
            db,
            action="asset.upload",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type="asset",
            target_id=asset.id,
            details={"kind": kind, "size": size},
        )
        db.commit()
        return _serialize(asset)
    except Exception:
        db.rollback()
        if object_key:
            try:
                object_store.delete(object_key)
            except Exception:
                pass
        raise
    finally:
        temp_path.unlink(missing_ok=True)
        file.file.close()


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return _serialize(_owned_asset(db, principal.tenant_id, asset_id))


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
):
    asset = _owned_asset(db, principal.tenant_id, asset_id)
    signed = object_store.signed_get_url(asset.object_key)
    if signed:
        return RedirectResponse(signed, status_code=307)
    path = object_store.local_path(asset.object_key)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Asset bytes not found")
    return FileResponse(path, media_type=asset.content_type, filename=asset.name)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    asset = _owned_asset(db, principal.tenant_id, asset_id)
    _assert_not_referenced(db, asset)
    object_store.delete(asset.object_key)
    db.delete(asset)
    audit(db, action="asset.delete", tenant_id=principal.tenant_id, user_id=principal.user_id, target_type="asset", target_id=asset.id)
    db.commit()
