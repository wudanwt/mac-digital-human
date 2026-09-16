from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .admin_api import router as admin_router
from .assets_api import router as assets_router
from .auth_api import router as auth_router
from .auth_api import workspace_router
from .billing_api import router as billing_router
from .compliance_api import admin_router as admin_compliance_router
from .compliance_api import router as compliance_router
from .database import engine
from .digital_human_api import router as digital_human_router
from .settings import saas_settings
from .storage import object_store
from .studio_api import avatar_router, course_router, dashboard_router, job_router, voice_router


router = APIRouter(prefix=saas_settings.api_prefix)


@router.get("/health", tags=["system"])
def health() -> dict:
    checks: dict[str, str] = {}
    failures: list[str] = []

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = "error"
        failures.append(f"database: {exc}")

    if saas_settings.worker_backend == "redis":
        try:
            import redis

            client = redis.Redis.from_url(saas_settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = "error"
            failures.append(f"redis: {exc}")
    else:
        checks["redis"] = "not-required"

    try:
        object_store.healthcheck()
        checks["storage"] = "ok"
    except Exception as exc:
        checks["storage"] = "error"
        failures.append(f"storage: {exc}")

    payload = {
        "status": "ok" if not failures else "degraded",
        "service": saas_settings.app_name,
        "environment": saas_settings.environment,
        "worker_backend": saas_settings.worker_backend,
        "storage_backend": saas_settings.storage_backend,
        "version": "0.5.0",
        "checks": checks,
    }
    if failures:
        raise HTTPException(status_code=503, detail={**payload, "failures": failures})
    return payload


@router.get("/capabilities", tags=["system"])
def capabilities() -> dict:
    return {
        "auth": True,
        "multi_tenant": True,
        "assets": True,
        "digital_human_assets": True,
        "digital_human_direct_upload": True,
        "browser_voice_recording": True,
        "avatars": True,
        "voice_profiles": True,
        "courses": True,
        "render_queue": True,
        "usage_quota": True,
        "plans": True,
        "admin": True,
        "consent_records": True,
        "content_reports": True,
        "ai_content_label": saas_settings.require_ai_label,
        "object_storage": ["s3", "minio", "oss", "cos"],
        "cuda_worker": "skipped-pending-hardware-validation",
        "payment_providers": list(saas_settings.payment_providers),
    }


for child in (
    auth_router,
    workspace_router,
    assets_router,
    digital_human_router,
    voice_router,
    avatar_router,
    course_router,
    job_router,
    dashboard_router,
    billing_router,
    compliance_router,
    admin_router,
    admin_compliance_router,
):
    router.include_router(child)
