from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .compliance_models import ContentReport
from .database import get_db
from .models import Asset, Avatar, ConsentRecord, Course, RenderJobRecord, VoiceProfile
from .security import Principal, get_principal, require_admin, require_superuser
from .services import audit, utcnow


router = APIRouter(prefix="/compliance", tags=["compliance"])
admin_router = APIRouter(prefix="/admin/compliance", tags=["admin", "compliance"])


class ReportCreate(BaseModel):
    target_type: str = Field(pattern="^(asset|course|job)$")
    target_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=5000)


class ReportResolve(BaseModel):
    status: str = Field(pattern="^(reviewing|resolved|rejected)$")
    resolution: str = Field(default="", max_length=5000)


def _target_exists(db: Session, tenant_id: str, target_type: str, target_id: str) -> bool:
    if target_type == "asset":
        return bool(db.scalar(select(Asset.id).where(Asset.id == target_id, Asset.tenant_id == tenant_id)))
    if target_type == "course":
        return bool(db.scalar(select(Course.id).where(Course.id == target_id, Course.tenant_id == tenant_id)))
    if target_type == "job":
        return bool(
            db.scalar(select(RenderJobRecord.id).where(RenderJobRecord.id == target_id, RenderJobRecord.tenant_id == tenant_id))
        )
    return False


def _report_dict(item: ContentReport) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "user_id": item.user_id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "reason": item.reason,
        "details": item.details,
        "status": item.status,
        "resolution": item.resolution,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/consents")
def list_consents(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    rows = db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.tenant_id == principal.tenant_id)
        .order_by(ConsentRecord.created_at.desc())
    ).all()
    return [
        {
            "id": item.id,
            "subject_type": item.subject_type,
            "subject_id": item.subject_id,
            "consent_type": item.consent_type,
            "statement": item.statement,
            "created_at": item.created_at.isoformat(),
            "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
        }
        for item in rows
    ]


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(
    consent_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = db.scalar(
        select(ConsentRecord).where(
            ConsentRecord.id == consent_id,
            ConsentRecord.tenant_id == principal.tenant_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    if item.revoked_at is None:
        item.revoked_at = utcnow()
        if item.subject_type == "avatar":
            avatar = db.scalar(
                select(Avatar).where(Avatar.id == item.subject_id, Avatar.tenant_id == principal.tenant_id)
            )
            if avatar:
                avatar.status = "blocked"
                # Remove synthesis source links so any subsequent real render is rejected safely.
                avatar.master_video_asset_id = None
                avatar.image_asset_id = None
        elif item.subject_type == "voice":
            voice = db.scalar(
                select(VoiceProfile).where(VoiceProfile.id == item.subject_id, VoiceProfile.tenant_id == principal.tenant_id)
            )
            if voice:
                voice.reference_asset_id = None
                voice.transcript = ""
                voice.provider = "revoked"
                avatars = db.scalars(
                    select(Avatar).where(Avatar.tenant_id == principal.tenant_id, Avatar.voice_profile_id == voice.id)
                ).all()
                for avatar in avatars:
                    avatar.voice_profile_id = None
                courses = db.scalars(
                    select(Course).where(Course.tenant_id == principal.tenant_id, Course.voice_profile_id == voice.id)
                ).all()
                for course in courses:
                    course.voice_profile_id = None
        audit(
            db,
            action="consent.revoke",
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            target_type=item.subject_type,
            target_id=item.subject_id,
            details={"consent_id": item.id, "consent_type": item.consent_type},
        )
        db.commit()
    return {"id": item.id, "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None}


@router.post("/reports", status_code=201)
def create_report(
    body: ReportCreate,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if not _target_exists(db, principal.tenant_id, body.target_type, body.target_id):
        raise HTTPException(status_code=404, detail="Report target not found")
    item = ContentReport(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason.strip(),
        details=body.details.strip(),
    )
    db.add(item)
    db.flush()
    audit(
        db,
        action="compliance.report_create",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        target_type=body.target_type,
        target_id=body.target_id,
        details={"report_id": item.id, "reason": item.reason},
    )
    db.commit()
    return _report_dict(item)


@router.get("/reports")
def list_reports(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    stmt = select(ContentReport).where(ContentReport.tenant_id == principal.tenant_id)
    if principal.role == "member" and not principal.is_superuser:
        stmt = stmt.where(ContentReport.user_id == principal.user_id)
    rows = db.scalars(stmt.order_by(ContentReport.created_at.desc()).limit(200)).all()
    return [_report_dict(item) for item in rows]


@admin_router.get("/reports")
def admin_reports(
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
) -> list[dict]:
    del principal
    stmt = select(ContentReport)
    if status:
        stmt = stmt.where(ContentReport.status == status)
    rows = db.scalars(stmt.order_by(ContentReport.created_at.desc()).limit(500)).all()
    return [_report_dict(item) for item in rows]


@admin_router.patch("/reports/{report_id}")
def resolve_report(
    report_id: str,
    body: ReportResolve,
    principal: Annotated[Principal, Depends(require_superuser)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = db.get(ContentReport, report_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Report not found")
    item.status = body.status
    item.resolution = body.resolution.strip()
    audit(
        db,
        action="compliance.report_update",
        tenant_id=item.tenant_id,
        user_id=principal.user_id,
        target_type="report",
        target_id=item.id,
        details={"status": item.status, "resolution": item.resolution},
    )
    db.commit()
    return _report_dict(item)
