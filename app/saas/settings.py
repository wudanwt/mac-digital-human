from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SaaSSettings:
    """Environment-driven settings for the cloud edition.

    Defaults deliberately keep local development easy while production values
    are supplied through environment variables or a secret manager.
    """

    environment: str = os.getenv("SAAS_ENV", "development")
    api_prefix: str = os.getenv("SAAS_API_PREFIX", "/api/saas")

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://digital_human:digital_human@127.0.0.1:5432/digital_human",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    queue_name: str = os.getenv("SAAS_QUEUE_NAME", "avatar:render")

    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    storage_bucket: str = os.getenv("STORAGE_BUCKET", "digital-human")
    storage_endpoint: str | None = os.getenv("STORAGE_ENDPOINT")
    storage_region: str | None = os.getenv("STORAGE_REGION")
    storage_public_base_url: str | None = os.getenv("STORAGE_PUBLIC_BASE_URL")

    worker_backend: str = os.getenv("WORKER_BACKEND", "local")
    worker_poll_timeout_seconds: int = int(os.getenv("WORKER_POLL_TIMEOUT_SECONDS", "5"))
    allow_local_fallback: bool = _env_bool("SAAS_ALLOW_LOCAL_FALLBACK", True)

    tenant_header: str = os.getenv("SAAS_TENANT_HEADER", "X-Tenant-ID")
    user_header: str = os.getenv("SAAS_USER_HEADER", "X-User-ID")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


saas_settings = SaaSSettings()
