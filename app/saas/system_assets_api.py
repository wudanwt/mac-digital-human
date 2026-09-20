from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .database import get_db
from .models import SystemAssetTemplate
from .security import Principal, get_principal
from .settings import saas_settings
from .storage import object_store
from .system_assets import import_template


router = APIRouter(prefix="/system-assets", tags=["system-assets"])


@router.get("")
def list_system_assets(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    kind: str | None = None,
) -> list[dict]:
    del principal
    stmt = select(SystemAssetTemplate).where(SystemAssetTemplate.is_active.is_(True))
    if kind:
        if kind not in {"avatar", "background"}:
            raise HTTPException(status_code=422, detail="Unsupported system asset kind")
        stmt = stmt.where(SystemAssetTemplate.kind == kind)
    items = db.scalars(stmt.order_by(SystemAssetTemplate.kind, SystemAssetTemplate.name)).all()
    return [
        {"id": item.id, "kind": item.kind, "name": item.name,
         "preview_url": f"{saas_settings.api_prefix}/system-assets/{item.id}/preview"}
        for item in items
    ]


@router.get("/{template_id}/preview")
def system_asset_preview(
    template_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
):
    del principal
    item = db.get(SystemAssetTemplate, template_id)
    if item is None or not item.is_active:
        raise HTTPException(status_code=404, detail="System asset not found")
    media = json.loads(item.metadata_json)["media"]
    descriptor = media.get("background") or media.get("image")
    if descriptor is None:
        raise HTTPException(status_code=404, detail="Preview not available")
    key = descriptor["key"]
    path = object_store.local_path(key)
    background = None
    if path is None:
        suffix = Path(descriptor.get("name") or key).suffix or ".bin"
        fd, temp_name = tempfile.mkstemp(prefix="saas-system-preview-", suffix=suffix)
        os.close(fd)
        path = Path(temp_name)
        try:
            object_store.materialize(key, path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        background = BackgroundTask(path.unlink, missing_ok=True)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview bytes not found")
    return FileResponse(path, media_type=descriptor["content_type"], background=background)


@router.post("/{template_id}/import")
def import_system_asset(
    template_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return import_template(db, principal, template_id)
