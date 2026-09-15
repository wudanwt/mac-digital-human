from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class SaaSSettings:
    environment: str = os.getenv("SAAS_ENV", "development")
    api_prefix: str = os.getenv("SAAS_API_PREFIX", "/api/saas")
    app_name: str = os.getenv("SAAS_APP_NAME", "Digital Human SaaS Studio")

    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(ROOT / 'workspace' / 'saas.db').as_posix()}",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    queue_name: str = os.getenv("SAAS_QUEUE_NAME", "avatar:render")
    queue_stale_seconds: int = int(os.getenv("SAAS_QUEUE_STALE_SECONDS", "7200"))

    jwt_secret: str = os.getenv("SAAS_JWT_SECRET", "dev-change-me-before-production")
    jwt_algorithm: str = os.getenv("SAAS_JWT_ALGORITHM", "HS256")
    access_token_minutes: int = int(os.getenv("SAAS_ACCESS_TOKEN_MINUTES", "1440"))
    admin_emails: tuple[str, ...] = _env_list("SAAS_ADMIN_EMAILS")
    allow_public_registration: bool = _env_bool("SAAS_ALLOW_PUBLIC_REGISTRATION", True)

    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    storage_bucket: str = os.getenv("STORAGE_BUCKET", "digital-human")
    storage_endpoint: str | None = os.getenv("STORAGE_ENDPOINT")
    storage_region: str | None = os.getenv("STORAGE_REGION")
    storage_public_base_url: str | None = os.getenv("STORAGE_PUBLIC_BASE_URL")
    storage_local_root: Path = Path(os.getenv("STORAGE_LOCAL_ROOT", str(ROOT / "workspace" / "saas-assets")))
    storage_signed_url_seconds: int = int(os.getenv("STORAGE_SIGNED_URL_SECONDS", "3600"))

    worker_backend: str = os.getenv("WORKER_BACKEND", "local")
    worker_poll_timeout_seconds: int = int(os.getenv("WORKER_POLL_TIMEOUT_SECONDS", "5"))
    allow_local_fallback: bool = _env_bool("SAAS_ALLOW_LOCAL_FALLBACK", True)

    max_upload_mb: int = int(os.getenv("SAAS_MAX_UPLOAD_MB", "500"))
    rate_limit_per_minute: int = int(os.getenv("SAAS_RATE_LIMIT_PER_MINUTE", "120"))
    cors_origins: tuple[str, ...] = _env_list("SAAS_CORS_ORIGINS", "http://localhost:8918,http://127.0.0.1:8918")
    trusted_hosts: tuple[str, ...] = _env_list("SAAS_TRUSTED_HOSTS", "*")

    free_plan_minutes: int = int(os.getenv("SAAS_FREE_PLAN_MINUTES", "30"))
    default_render_estimate_seconds: int = int(os.getenv("SAAS_DEFAULT_RENDER_ESTIMATE_SECONDS", "60"))
    max_free_workspaces_per_user: int = int(os.getenv("SAAS_MAX_FREE_WORKSPACES_PER_USER", "1"))

    payment_providers: tuple[str, ...] = _env_list("SAAS_PAYMENT_PROVIDERS", "manual")

    require_ai_label: bool = _env_bool("SAAS_REQUIRE_AI_LABEL", True)
    ai_label_text: str = os.getenv("SAAS_AI_LABEL_TEXT", "AI生成")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def validate_production(self) -> None:
        if not self.is_production:
            return
        forbidden_secrets = {
            "dev-change-me-before-production",
            "replace-with-a-long-random-production-secret",
            "CHANGE_ME_WITH_A_UNIQUE_RANDOM_SECRET",
            "ci-test-secret-not-for-production-1234567890",
        }
        if self.jwt_secret in forbidden_secrets or len(self.jwt_secret) < 32:
            raise RuntimeError("SAAS_JWT_SECRET must be a unique random 32+ character secret in production")
        if self.allow_public_registration:
            raise RuntimeError(
                "Public production registration is disabled until email verification is configured; "
                "set SAAS_ALLOW_PUBLIC_REGISTRATION=false and provision users with the admin CLI"
            )
        if self.database_url.startswith("sqlite"):
            raise RuntimeError("Production SaaS must use PostgreSQL")
        if self.worker_backend != "redis":
            raise RuntimeError("Production SaaS requires WORKER_BACKEND=redis")
        if self.storage_backend.lower() == "local":
            raise RuntimeError("Production SaaS requires private object storage instead of local disk")
        if not self.trusted_hosts or self.trusted_hosts == ("*",):
            raise RuntimeError("Production SaaS requires explicit SAAS_TRUSTED_HOSTS")
        if any(origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1") for origin in self.cors_origins):
            raise RuntimeError("Production SaaS must configure non-localhost SAAS_CORS_ORIGINS")
        if not self.require_ai_label:
            raise RuntimeError("Production SaaS requires AI-generated content labeling")
        unsupported = set(self.payment_providers) - {"manual"}
        if unsupported:
            raise RuntimeError(
                "Only manual payment is production-ready in this branch; "
                f"disable unsupported providers: {sorted(unsupported)}"
            )


saas_settings = SaaSSettings()
