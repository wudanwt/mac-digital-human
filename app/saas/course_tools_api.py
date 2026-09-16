from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ppt import PresentationParser, PPTRenderer
from .database import get_db
from .models import Asset, Avatar, ConsentRecord, Course, VoiceProfile
from .security import Principal, get_principal
from .services import audit
from .storage import object_store


router = APIRouter(prefix="/course-tools", tags=["course-tools"])


def _course(db: Session, tenant_id: str, course_id: str) -> Course:
    item = db.scalar(select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return item


def _asset(db: Session, tenant_id: str, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    return db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))


def _active_consent(db: Session, tenant_id: str, subject_type: str, subject_id: str) -> bool:
    return bool(
        db.scalar(
            select(ConsentRecord.id)
            .where(
                ConsentRecord.tenant_id == tenant_id,
                ConsentRecord.subject_type == subject_type,
                ConsentRecord.subject_id == subject_id,
                ConsentRecord.revoked_at.is_(None),
            )
            .limit(1)
        )
    )


def _preview_key(tenant_id: str, asset_id: str, index: int) -> str:
    return f"{tenant_id}/course-previews/{asset_id}/slide_{index:03d}.png"


def _render_previews(asset: Asset, tenant_id: str) -> tuple[object, list[Path]]:
    suffix = Path(asset.name).suffix.lower() or ".pptx"
    temp = tempfile.TemporaryDirectory(prefix="saas-course-preview-")
    root = Path(temp.name)
    local = root / f"course{suffix}"
    object_store.materialize(asset.object_key, local)
    deck = PresentationParser.parse(local)
    rendered = PPTRenderer.render_deck(deck, root / "slides", width=1280, height=720)
    for index, image in enumerate(rendered, start=1):
        object_store.put_file(image, _preview_key(tenant_id, asset.id, index))
    # The TemporaryDirectory must stay alive until callers have consumed metadata.
    deck._preview_temp = temp  # type: ignore[attr-defined]
    return deck, rendered


@router.get("/ppt/{asset_id}/outline")
def ppt_outline(
    asset_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    asset = _asset(db, principal.tenant_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="PPT asset not found")
    if asset.kind not in {"ppt", "document"} or Path(asset.name).suffix.lower() not in {".pptx", ".ppt", ".pdf"}:
        raise HTTPException(status_code=422, detail="Asset is not a supported PPT/PDF course file")

    try:
        deck, _ = _render_previews(asset, principal.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Course file could not be parsed/rendered: {exc}") from exc

    return {
        "asset_id": asset.id,
        "title": deck.title,
        "total_slides": deck.total_slides,
        "slides": [
            {
                "index": slide.index,
                "title": slide.title,
                "bullets": slide.bullets,
                "notes": slide.notes,
                "narration": slide.narration,
                "layout": slide.layout,
                "thumbnail_url": f"/api/saas/course-tools/ppt/{asset.id}/slides/{slide.index}/thumbnail",
            }
            for slide in deck.slides
        ],
    }


@router.get("/ppt/{asset_id}/slides/{slide_index}/thumbnail")
def ppt_thumbnail(
    asset_id: str,
    slide_index: int,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
):
    asset = _asset(db, principal.tenant_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="PPT asset not found")
    if slide_index < 1:
        raise HTTPException(status_code=404, detail="Slide not found")
    key = _preview_key(principal.tenant_id, asset_id, slide_index)
    signed = object_store.signed_get_url(key)
    if signed:
        return RedirectResponse(signed, status_code=307)
    path = object_store.local_path(key)
    if path is None or not path.exists():
        try:
            deck, _ = _render_previews(asset, principal.tenant_id)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Slide preview unavailable: {exc}") from exc
        if slide_index > deck.total_slides:
            raise HTTPException(status_code=404, detail="Slide not found")
        path = object_store.local_path(key)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Slide preview bytes not found")
    return FileResponse(path, media_type="image/png", filename=f"slide_{slide_index:03d}.png")


@router.get("/courses/{course_id}/readiness")
def course_readiness(
    course_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course = _course(db, principal.tenant_id, course_id)
    issues: list[str] = []
    ppt = _asset(db, principal.tenant_id, course.ppt_asset_id)
    avatar = db.scalar(
        select(Avatar).where(Avatar.id == course.avatar_id, Avatar.tenant_id == principal.tenant_id)
    ) if course.avatar_id else None

    if ppt is None:
        issues.append("请配置课程 PPT")
    elif Path(ppt.name).suffix.lower() not in {".pptx", ".ppt", ".pdf"}:
        issues.append("课程素材不是有效的 PPT/PDF")

    if avatar is None:
        issues.append("请选择数字人")
    else:
        if avatar.status != "ready":
            issues.append("数字人当前不可用")
        if not avatar.master_video_asset_id:
            issues.append("数字人缺少母版视频")
        if not _active_consent(db, principal.tenant_id, "avatar", avatar.id):
            issues.append("数字人肖像/视频授权不可用")

    voice_id = course.voice_profile_id or (avatar.voice_profile_id if avatar else None)
    voice = db.scalar(
        select(VoiceProfile).where(VoiceProfile.id == voice_id, VoiceProfile.tenant_id == principal.tenant_id)
    ) if voice_id else None
    if voice is None:
        issues.append("数字人缺少可用声音")
    else:
        ref = _asset(db, principal.tenant_id, voice.reference_asset_id)
        if voice.provider == "revoked" or ref is None or ref.kind != "audio" or not voice.transcript.strip():
            issues.append("克隆声音配置不完整")
        if not _active_consent(db, principal.tenant_id, "voice", voice.id):
            issues.append("声音克隆授权不可用")

    script = json.loads(course.script_json or "[]")
    if not script:
        issues.append("课程讲稿尚未生成或编辑")

    return {
        "course_id": course.id,
        "ready": not issues,
        "issues": issues,
        "effective_voice_profile_id": voice.id if voice else None,
        "slide_script_count": len(script),
    }


@router.post("/courses/{course_id}/normalize")
def normalize_course(
    course_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course = _course(db, principal.tenant_id, course_id)
    avatar = db.scalar(
        select(Avatar).where(Avatar.id == course.avatar_id, Avatar.tenant_id == principal.tenant_id)
    ) if course.avatar_id else None
    changed = False
    if course.voice_profile_id is None and avatar and avatar.voice_profile_id:
        course.voice_profile_id = avatar.voice_profile_id
        changed = True
    if changed:
        audit(
            db,
            action="course.normalize",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type="course",
            target_id=course.id,
            details={"voice_profile_id": course.voice_profile_id},
        )
        db.commit()
    return {
        "id": course.id,
        "voice_profile_id": course.voice_profile_id,
        "changed": changed,
    }
