from dataclasses import replace

import pytest

from app.saas.settings import saas_settings


def _production_settings(**changes):
    base = replace(
        saas_settings,
        environment="production",
        jwt_secret="a-unique-production-secret-that-is-definitely-long-enough-123",
        allow_public_registration=False,
        database_url="postgresql+psycopg://user:pass@db:5432/app",
        worker_backend="redis",
        storage_backend="s3",
        trusted_hosts=("saas.example.com",),
        cors_origins=("https://saas.example.com",),
        payment_providers=("manual",),
        require_ai_label=True,
    )
    return replace(base, **changes)


def test_production_rejects_example_jwt_secret() -> None:
    settings = _production_settings(jwt_secret="CHANGE_ME_WITH_A_UNIQUE_RANDOM_SECRET")
    with pytest.raises(RuntimeError, match="SAAS_JWT_SECRET"):
        settings.validate_production()


def test_production_rejects_unverified_public_registration() -> None:
    settings = _production_settings(allow_public_registration=True)
    with pytest.raises(RuntimeError, match="Public production registration"):
        settings.validate_production()


def test_production_rejects_local_storage() -> None:
    settings = _production_settings(storage_backend="local")
    with pytest.raises(RuntimeError, match="object storage"):
        settings.validate_production()


def test_production_rejects_unimplemented_payment_provider() -> None:
    settings = _production_settings(payment_providers=("manual", "wechat"))
    with pytest.raises(RuntimeError, match="Only manual payment"):
        settings.validate_production()


def test_production_safe_configuration_passes() -> None:
    _production_settings().validate_production()
