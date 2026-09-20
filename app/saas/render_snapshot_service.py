from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from .avatar_matting_models import AvatarMattingJob
from .media_cues import media_cue_asset_ids
from .models import Asset, Avatar, Course, RenderJobRecord, VoiceProfile
from .render_snapshot_models import RenderTaskSnapshot
from .speech_preview_models import SpeechPreviewJob
from .speech_preview_service import synthesis_fingerprint

SNAPSHOT_SCHEMA_VERSION = 1


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_by_id(connection: Connection, model, row_id: str | None, tenant_id: str) -> dict[str, Any] | None:
    if not row_id:
        return None
    table = model.__table__
    stmt = select(table).where(table.c.id == row_id)
    if "tenant_id" in table.c:
        stmt = stmt.where(table.c.tenant_id == tenant_id)
    row = connection.execute(stmt).mappings().first()
    return dict(row) if row else None


def _asset_entry(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "kind": row.get("kind"),
        "name": row.get("name"),
        "content_type": row.get("content_type"),
        "size_bytes": int(row.get("size_bytes") or 0),
        "sha256": row.get("sha256") or "",
        "status": row.get("status") or "",
    }


def _page_narration(item: dict[str, Any], index: int) -> str:
    return str(item.get("narration") or item.get("script") or f"第{index}页").strip()


def _voice_proxy(row: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=row["id"],
        provider=row.get("provider") or "cosyvoice",
        reference_asset_id=row.get("reference_asset_id"),
        transcript=row.get("transcript") or "",
        settings_json=row.get("settings_json") or "{}",
        updated_at=row.get("updated_at"),
    )


def _matching_preview_asset_id(
    connection: Connection,
    *,
    tenant_id: str,
    course_id: str,
    slide_index: int,
    text: str,
    voice_row: dict[str, Any] | None,
    course_settings: dict[str, Any],
) -> str | None:
    if voice_row is None:
        return None
    digest = synthesis_fingerprint(
        text=text,
        scope="page",
        voice=_voice_proxy(voice_row),
        course_settings=course_settings,
    )
    table = SpeechPreviewJob.__table__
    row = connection.execute(
        select(table)
        .where(
            table.c.tenant_id == tenant_id,
            table.c.course_id == course_id,
            table.c.slide_index == slide_index,
            table.c.scope == "page",
            table.c.text_hash == digest,
            table.c.status == "succeeded",
            table.c.audio_asset_id.is_not(None),
        )
        .order_by(table.c.completed_at.desc())
        .limit(1)
    ).mappings().first()
    return str(row["audio_asset_id"]) if row and row.get("audio_asset_id") else None


def _latest_alpha_asset_id(
    connection: Connection,
    *,
    tenant_id: str,
    avatar_id: str | None,
    master_video_asset_id: str | None,
) -> str | None:
    if not avatar_id or not master_video_asset_id:
        return None
    table = AvatarMattingJob.__table__
    row = connection.execute(
        select(table)
        .where(
            table.c.tenant_id == tenant_id,
            table.c.avatar_id == avatar_id,
            table.c.source_asset_id == master_video_asset_id,
            table.c.status == "succeeded",
            table.c.alpha_asset_id.is_not(None),
        )
        .order_by(table.c.created_at.desc())
        .limit(1)
    ).mappings().first()
    return str(row["alpha_asset_id"]) if row and row.get("alpha_asset_id") else None


def build_snapshot_payload(connection: Connection, record: RenderJobRecord) -> dict[str, Any] | None:
    """Build a deterministic immutable snapshot inside the render-job transaction."""

    payload = _loads(record.payload_json, {})
    if not isinstance(payload, dict) or payload.get("job_type") != "course_render":
        return None
    course_id = str(payload.get("course_id") or record.course_id or "")
    if not course_id:
        return None

    tenant_id = record.tenant_id
    course_row = _row_by_id(connection, Course, course_id, tenant_id)
    avatar_row = _row_by_id(connection, Avatar, payload.get("avatar_id"), tenant_id)
    voice_row = _row_by_id(connection, VoiceProfile, payload.get("voice_profile_id"), tenant_id)

    script = payload.get("script") if isinstance(payload.get("script"), list) else []
    course_settings = payload.get("course_settings") if isinstance(payload.get("course_settings"), dict) else {}
    master_video_asset_id = str(payload.get("master_video_asset_id") or (avatar_row or {}).get("master_video_asset_id") or "") or None
    ppt_asset_id = str(payload.get("ppt_asset_id") or (course_row or {}).get("ppt_asset_id") or "") or None
    direct_audio_asset_id = str(payload.get("audio_asset_id") or "") or None
    reference_asset_id = str((voice_row or {}).get("reference_asset_id") or "") or None

    global_mode = str(course_settings.get("avatar_mode") or "original").strip().lower()
    pages: list[dict[str, Any]] = []
    asset_ids: set[str] = {
        value
        for value in (ppt_asset_id, master_video_asset_id, direct_audio_asset_id, reference_asset_id)
        if value
    }
    needs_alpha = False

    for position, raw in enumerate(script, start=1):
        item = dict(raw) if isinstance(raw, dict) else {}
        index = int(item.get("index") or position)
        narration = _page_narration(item, index)
        avatar_mode = str(item.get("avatar_mode") or global_mode or "original").strip().lower()
        if avatar_mode not in {"original", "transparent", "white"}:
            avatar_mode = "original"
        needs_alpha = needs_alpha or avatar_mode in {"transparent", "white"}

        explicit_audio = str(item.get("audio_asset_id") or "") or None
        preview_audio = None
        if explicit_audio is None and direct_audio_asset_id is None:
            preview_audio = _matching_preview_asset_id(
                connection,
                tenant_id=tenant_id,
                course_id=course_id,
                slide_index=index,
                text=narration,
                voice_row=voice_row,
                course_settings=course_settings,
            )
        background_asset_id = str(item.get("background_asset_id") or "") or None
        media_cues = item.get("media_cues") if isinstance(item.get("media_cues"), list) else []
        cue_asset_ids = media_cue_asset_ids(media_cues)
        for value in (explicit_audio, preview_audio, background_asset_id, *sorted(cue_asset_ids)):
            if value:
                asset_ids.add(value)

        pages.append(
            {
                "index": index,
                "narration": narration,
                "layout": str(item.get("layout") or course_settings.get("layout") or "pip"),
                "avatar_mode": avatar_mode,
                "explicit_audio_asset_id": explicit_audio,
                "preview_audio_asset_id": preview_audio,
                "background_asset_id": background_asset_id,
                "media_cues": media_cues,
                "settings": item,
            }
        )

    alpha_asset_id = _latest_alpha_asset_id(
        connection,
        tenant_id=tenant_id,
        avatar_id=str(payload.get("avatar_id") or "") or None,
        master_video_asset_id=master_video_asset_id,
    ) if needs_alpha else None
    if alpha_asset_id:
        asset_ids.add(alpha_asset_id)

    assets: dict[str, Any] = {}
    for asset_id in sorted(asset_ids):
        row = _row_by_id(connection, Asset, asset_id, tenant_id)
        entry = _asset_entry(row)
        if entry is not None:
            assets[asset_id] = entry

    voice_payload = None
    if voice_row is not None:
        voice_payload = {
            "id": voice_row["id"],
            "provider": voice_row.get("provider") or "cosyvoice",
            "reference_asset_id": voice_row.get("reference_asset_id"),
            "transcript": voice_row.get("transcript") or "",
            "settings": _loads(voice_row.get("settings_json"), {}),
            "updated_at": voice_row.get("updated_at").isoformat() if voice_row.get("updated_at") else None,
        }

    frozen = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "job_id": record.id,
        "tenant_id": tenant_id,
        "user_id": record.user_id,
        "course_id": course_id,
        "engine": record.engine,
        "course": {
            "title": (course_row or {}).get("title") or "",
            "script": script,
            "settings": course_settings,
        },
        "avatar": {
            "id": payload.get("avatar_id"),
            "master_video_asset_id": master_video_asset_id,
            "image_asset_id": (avatar_row or {}).get("image_asset_id"),
            "voice_profile_id": (avatar_row or {}).get("voice_profile_id"),
        },
        "voice": voice_payload,
        "ppt_asset_id": ppt_asset_id,
        "direct_audio_asset_id": direct_audio_asset_id,
        "alpha_required": needs_alpha,
        "alpha_asset_id": alpha_asset_id,
        "pages": pages,
        "assets": assets,
        "render_contract": {
            "version": os.getenv("SAAS_RENDER_CONTRACT_VERSION", "v1"),
            "renderer": record.engine,
            "tts_prefetch": False,
        },
    }
    frozen["snapshot_hash"] = _canonical_hash(frozen)
    return frozen


@event.listens_for(RenderJobRecord, "after_insert")
def _capture_render_snapshot(_mapper, connection: Connection, target: RenderJobRecord) -> None:
    """Capture once, atomically with the parent job and quota reservation."""

    frozen = build_snapshot_payload(connection, target)
    if frozen is None:
        return
    table = RenderTaskSnapshot.__table__
    connection.execute(
        table.insert().values(
            job_id=target.id,
            tenant_id=target.tenant_id,
            course_id=frozen["course_id"],
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            snapshot_hash=frozen["snapshot_hash"],
            snapshot_json=json.dumps(frozen, ensure_ascii=False, sort_keys=True),
            created_at=target.created_at,
        )
    )


def load_snapshot_payload(db: Session, job_id: str) -> dict[str, Any] | None:
    row = db.get(RenderTaskSnapshot, job_id)
    if row is None:
        return None
    payload = _loads(row.snapshot_json, {})
    return payload if isinstance(payload, dict) else None


def _parse_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _frozen_voice(snapshot: dict[str, Any]) -> SimpleNamespace | None:
    voice = snapshot.get("voice")
    if not isinstance(voice, dict) or not voice.get("id"):
        return None
    return SimpleNamespace(
        id=voice["id"],
        provider=voice.get("provider") or "cosyvoice",
        reference_asset_id=voice.get("reference_asset_id"),
        transcript=voice.get("transcript") or "",
        settings_json=json.dumps(voice.get("settings") or {}, ensure_ascii=False),
        updated_at=_parse_datetime(voice.get("updated_at")),
    )


def _checked_asset(db: Session, tenant_id: str, snapshot: dict[str, Any], asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))
    if asset is None:
        raise RuntimeError(f"snapshot asset missing: {asset_id}")
    expected = ((snapshot.get("assets") or {}).get(asset_id) or {}).get("sha256")
    if expected and asset.sha256 and asset.sha256 != expected:
        raise RuntimeError(f"snapshot asset hash changed: {asset_id}")
    return asset


@dataclass
class ResolvedRenderInputs:
    course_id: str
    ppt_asset: Asset
    master_asset: Asset
    ref_asset: Asset | None
    direct_audio: Asset | None
    voice: Any | None
    script_entries: list[dict[str, Any]]
    settings_payload: dict[str, Any]
    preview_audio_by_slide: dict[int, str]
    snapshot: dict[str, Any] | None

    @property
    def immutable(self) -> bool:
        return self.snapshot is not None


def resolve_render_inputs(db: Session, job) -> ResolvedRenderInputs:
    """Resolve frozen inputs for new jobs, with a legacy fallback for old jobs."""

    snapshot = load_snapshot_payload(db, job.id)
    if snapshot is not None:
        course_id = str(snapshot.get("course_id") or "")
        ppt_asset = _checked_asset(db, job.tenant_id, snapshot, snapshot.get("ppt_asset_id"))
        master_asset = _checked_asset(
            db,
            job.tenant_id,
            snapshot,
            ((snapshot.get("avatar") or {}).get("master_video_asset_id")),
        )
        if ppt_asset is None:
            raise RuntimeError("snapshot PPT asset is required")
        if master_asset is None:
            raise RuntimeError("snapshot master video asset is required")
        voice = _frozen_voice(snapshot)
        ref_asset = _checked_asset(
            db,
            job.tenant_id,
            snapshot,
            (snapshot.get("voice") or {}).get("reference_asset_id") if snapshot.get("voice") else None,
        )
        direct_audio = _checked_asset(db, job.tenant_id, snapshot, snapshot.get("direct_audio_asset_id"))
        script = ((snapshot.get("course") or {}).get("script")) or []
        settings = ((snapshot.get("course") or {}).get("settings")) or {}
        previews = {
            int(page.get("index")): str(page.get("preview_audio_asset_id"))
            for page in (snapshot.get("pages") or [])
            if isinstance(page, dict) and page.get("preview_audio_asset_id")
        }
        return ResolvedRenderInputs(
            course_id=course_id,
            ppt_asset=ppt_asset,
            master_asset=master_asset,
            ref_asset=ref_asset,
            direct_audio=direct_audio,
            voice=voice,
            script_entries=[dict(item) for item in script if isinstance(item, dict)],
            settings_payload=dict(settings) if isinstance(settings, dict) else {},
            preview_audio_by_slide=previews,
            snapshot=snapshot,
        )

    course = db.scalar(
        select(Course).where(
            Course.id == job.payload.get("course_id"),
            Course.tenant_id == job.tenant_id,
        )
    )
    if course is None:
        raise RuntimeError("course not found")
    avatar = (
        db.scalar(select(Avatar).where(Avatar.id == course.avatar_id, Avatar.tenant_id == job.tenant_id))
        if course.avatar_id else None
    )
    voice_id = course.voice_profile_id or (avatar.voice_profile_id if avatar else None)
    voice = (
        db.scalar(select(VoiceProfile).where(VoiceProfile.id == voice_id, VoiceProfile.tenant_id == job.tenant_id))
        if voice_id else None
    )
    ppt_asset = _checked_asset(db, job.tenant_id, {}, course.ppt_asset_id)
    if ppt_asset is None:
        raise RuntimeError("course PPT asset is required")
    if avatar is None or not avatar.master_video_asset_id:
        raise RuntimeError("MuseTalk course requires avatar master video")
    master_asset = _checked_asset(db, job.tenant_id, {}, avatar.master_video_asset_id)
    if master_asset is None:
        raise RuntimeError("avatar master video asset missing")
    ref_asset = _checked_asset(db, job.tenant_id, {}, voice.reference_asset_id) if voice and voice.reference_asset_id else None
    direct_audio = _checked_asset(db, job.tenant_id, {}, job.payload.get("audio_asset_id"))
    return ResolvedRenderInputs(
        course_id=course.id,
        ppt_asset=ppt_asset,
        master_asset=master_asset,
        ref_asset=ref_asset,
        direct_audio=direct_audio,
        voice=voice,
        script_entries=_loads(course.script_json, []),
        settings_payload=_loads(course.settings_json, {}),
        preview_audio_by_slide={},
        snapshot=None,
    )
