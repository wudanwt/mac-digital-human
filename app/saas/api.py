from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .domain import RenderJob, TenantContext
from .queue import job_queue
from .settings import saas_settings


router = APIRouter(prefix=saas_settings.api_prefix, tags=["saas"])


class RenderJobCreate(BaseModel):
    engine: str = Field(default="musetalk", min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class RenderJobResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    engine: str
    status: str
    created_at: str
    updated_at: str
    output_uri: str | None = None
    error: str | None = None


def _context(
    tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> TenantContext:
    # Header-based identity is intentionally a temporary development adapter.
    # Production will replace this with verified JWT/session claims.
    if not tenant_id or not user_id:
        raise HTTPException(status_code=401, detail="Missing tenant/user identity headers")
    return TenantContext(tenant_id=tenant_id, user_id=user_id)


TenantDependency = Annotated[TenantContext, Depends(_context)]


def _response(job: RenderJob) -> RenderJobResponse:
    data = job.to_dict()
    data.pop("payload", None)
    return RenderJobResponse(**data)


@router.get("/health")
def saas_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": saas_settings.environment,
        "worker_backend": saas_settings.worker_backend,
        "storage_backend": saas_settings.storage_backend,
    }


@router.post("/jobs", response_model=RenderJobResponse, status_code=202)
def create_render_job(body: RenderJobCreate, context: TenantDependency) -> RenderJobResponse:
    job = RenderJob(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        engine=body.engine,
        payload=body.payload,
    )
    job_queue.enqueue(job)
    return _response(job)


@router.get("/jobs/{job_id}", response_model=RenderJobResponse)
def get_render_job(job_id: str, context: TenantDependency) -> RenderJobResponse:
    job = job_queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.tenant_id != context.tenant_id or job.user_id != context.user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return _response(job)
