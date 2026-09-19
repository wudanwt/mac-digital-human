"""Publish private tenant media as portable, read-only platform templates.

Template bytes live under a separate object-store prefix. Importing a template
copies those bytes into the requesting tenant; existing tenant-scoped APIs then
continue to enforce their normal ownership checks.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Asset, Avatar, ConsentRecord, SystemAssetImport, SystemAssetTemplate, VoiceProfile
from .security import Principal
from .services import audit, enforce_storage_limit
from .storage import object_store


def _asset_descriptor(asset: Asset) -> dict:
    return {
        "key": asset.object_key,
        "name": asset.name,
        "kind": asset.kind,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
    }


def _copy_object(source: dict, key: str) -> tuple[str, dict]:
    suffix = Path(source["name"]).suffix.lower() or ".bin"
    with tempfile.TemporaryDirectory(prefix="system-asset-") as temp:
        path = Path(temp) / f"media{suffix}"
        object_store.materialize(source["key"], path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if source["sha256"] and digest != source["sha256"]:
            raise RuntimeError(f"Source asset checksum mismatch: {source['name']}")
        if path.stat().st_size != source["size_bytes"]:
            raise RuntimeError(f"Source asset size mismatch: {source['name']}")
        uri = object_store.put_file(path, key)
    return uri, {**source, "key": key, "sha256": digest}


def publish_template(db: Session, *, kind: str, source_id: str) -> SystemAssetTemplate:
    """CLI-only promotion. Source and all dependencies must still be local to DB."""
    existing = db.scalar(select(SystemAssetTemplate).where(SystemAssetTemplate.kind == kind, SystemAssetTemplate.source_id == source_id))
    if existing:
        return existing
    if kind == "background":
        background = db.get(Asset, source_id)
        if background is None or background.kind != "background":
            raise ValueError(f"Background asset not found: {source_id}")
        name = background.name
        source = {"background": _asset_descriptor(background)}
        extra = {}
    elif kind == "avatar":
        avatar = db.get(Avatar, source_id)
        if avatar is None:
            raise ValueError(f"Avatar not found: {source_id}")
        name = avatar.name
        voice = db.get(VoiceProfile, avatar.voice_profile_id) if avatar.voice_profile_id else None
        source = {
            role: _asset_descriptor(asset)
            for role, asset in (
                ("image", db.get(Asset, avatar.image_asset_id) if avatar.image_asset_id else None),
                ("master_video", db.get(Asset, avatar.master_video_asset_id) if avatar.master_video_asset_id else None),
                ("reference_audio", db.get(Asset, voice.reference_asset_id) if voice and voice.reference_asset_id else None),
            )
            if asset is not None
        }
        for descriptor in source.values():
            dependency = db.scalar(select(Asset).where(Asset.object_key == descriptor["key"]))
            if dependency is None or dependency.tenant_id != avatar.tenant_id:
                raise ValueError(f"Avatar dependency is outside its workspace: {source_id}")
        if not source.get("image") and not source.get("master_video"):
            raise ValueError(f"Avatar has no usable media: {source_id}")
        extra = {
            "prompt": avatar.prompt,
            "voice": {
                "name": voice.name,
                "provider": voice.provider,
                "transcript": voice.transcript,
                "settings_json": voice.settings_json,
            } if voice else None,
        }
    else:
        raise ValueError(f"Unsupported system template kind: {kind}")

    template = SystemAssetTemplate(id=uuid4().hex, kind=kind, source_id=source_id, name=name, metadata_json="{}")
    copied: list[str] = []
    try:
        media = {}
        for role, descriptor in source.items():
            key = f"system-defaults/{template.id}/{role}{Path(descriptor['name']).suffix.lower() or '.bin'}"
            _, media[role] = _copy_object(descriptor, key)
            copied.append(key)
        template.metadata_json = json.dumps({"media": media, **extra}, ensure_ascii=False)
        db.add(template)
        db.commit()
        return template
    except Exception:
        db.rollback()
        for key in copied:
            object_store.delete(key)
        raise


def _import_media(db: Session, principal: Principal, source: dict, copied: list[str]) -> Asset:
    enforce_storage_limit(db, principal.tenant_id, incoming_bytes=source["size_bytes"])
    key = f"{principal.tenant_id}/{source['kind']}/{uuid4().hex}{Path(source['name']).suffix.lower() or '.bin'}"
    uri, descriptor = _copy_object(source, key)
    copied.append(key)
    asset = Asset(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        kind=descriptor["kind"],
        name=descriptor["name"],
        object_key=key,
        uri=uri,
        content_type=descriptor["content_type"],
        size_bytes=descriptor["size_bytes"],
        sha256=descriptor["sha256"],
    )
    db.add(asset)
    db.flush()
    return asset


def import_template(db: Session, principal: Principal, template_id: str) -> dict:
    template = db.get(SystemAssetTemplate, template_id)
    if template is None or not template.is_active:
        raise HTTPException(status_code=404, detail="System asset not found")
    previous = db.scalar(select(SystemAssetImport).where(SystemAssetImport.tenant_id == principal.tenant_id, SystemAssetImport.template_id == template_id))
    if previous:
        model = Avatar if template.kind == "avatar" else Asset
        if db.get(model, previous.imported_id):
            return {"kind": template.kind, "id": previous.imported_id, "imported": False}
        db.delete(previous)
        db.flush()
    metadata = json.loads(template.metadata_json)
    media = metadata["media"]
    copied: list[str] = []
    try:
        if template.kind == "background":
            imported_id = _import_media(db, principal, media["background"], copied).id
        elif template.kind == "avatar":
            assets = {role: _import_media(db, principal, source, copied) for role, source in media.items()}
            voice_data = metadata.get("voice")
            voice = None
            if voice_data:
                voice = VoiceProfile(
                    tenant_id=principal.tenant_id,
                    name=voice_data["name"],
                    provider=voice_data["provider"],
                    reference_asset_id=assets.get("reference_audio").id if assets.get("reference_audio") else None,
                    transcript=voice_data["transcript"],
                    settings_json=voice_data["settings_json"],
                )
                db.add(voice)
                db.flush()
                db.add(ConsentRecord(tenant_id=principal.tenant_id, user_id=principal.user_id,
                                     subject_type="voice", subject_id=voice.id,
                                     consent_type="platform_default_license",
                                     statement="Platform-licensed system default voice."))
            avatar = Avatar(
                tenant_id=principal.tenant_id,
                name=template.name,
                image_asset_id=assets.get("image").id if assets.get("image") else None,
                master_video_asset_id=assets.get("master_video").id if assets.get("master_video") else None,
                voice_profile_id=voice.id if voice else None,
                prompt=metadata.get("prompt") or "",
            )
            db.add(avatar)
            db.flush()
            db.add(ConsentRecord(tenant_id=principal.tenant_id, user_id=principal.user_id,
                                 subject_type="avatar", subject_id=avatar.id,
                                 consent_type="platform_default_license",
                                 statement="Platform-licensed system default digital human."))
            imported_id = avatar.id
        else:
            raise HTTPException(status_code=422, detail="Unsupported system asset kind")
        db.add(SystemAssetImport(tenant_id=principal.tenant_id, template_id=template_id, imported_id=imported_id))
        audit(db, action="system_asset.import", tenant_id=principal.tenant_id, user_id=principal.user_id,
              target_type=template.kind, target_id=imported_id, details={"template_id": template_id})
        db.commit()
        return {"kind": template.kind, "id": imported_id, "imported": True}
    except Exception:
        db.rollback()
        for key in copied:
            object_store.delete(key)
        raise
