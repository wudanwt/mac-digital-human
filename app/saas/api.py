from __future__ import annotations

from fastapi import APIRouter

from .admin_api import router as admin_router
from .assets_api import router as assets_router
from .auth_api import router as auth_router
from .auth_api import workspace_router
from .billing_api import router as billing_router
from .settings import saas_settings
from .studio_api import avatar_router, course_router, dashboard_router, job_router, voice_router


router = APIRouter(prefix=saas_settings.api_prefix)


@router.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": saas_settings.app_name,
        "environment": saas_settings.environment,
        "worker_backend": saas_settings.worker_backend,
        "storage_backend": saas_settings.storage_backend,
        "version": "0.5.0",
    }


@router.get("/capabilities", tags=["system"])
def capabilities() -> dict:
    return {
        "auth": True,
        "multi_tenant": True,
        "assets": True,
        "avatars": True,
        "voice_profiles": True,
        "courses": True,
        "render_queue": True,
        "usage_quota": True,
        "plans": True,
        "admin": True,
        "cuda_worker": "adapter-ready-not-benchmarked",
        "payment_providers": ["manual", "mock", "wechat-adapter", "alipay-adapter"],
    }


for child in (
    auth_router,
    workspace_router,
    assets_router,
    voice_router,
    avatar_router,
    course_router,
    job_router,
    dashboard_router,
    billing_router,
    admin_router,
):
    router.include_router(child)
