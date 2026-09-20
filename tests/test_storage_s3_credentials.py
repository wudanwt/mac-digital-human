from __future__ import annotations

from types import SimpleNamespace

import boto3

from app.saas.storage import S3ObjectStore


def test_s3_store_uses_production_storage_credentials(monkeypatch) -> None:
    captured = {}

    def fake_client(service, **kwargs):
        captured["service"] = service
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("STORAGE_ACCESS_KEY", "test-access")
    monkeypatch.setenv("STORAGE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(boto3, "client", fake_client)

    S3ObjectStore()

    assert captured["service"] == "s3"
    assert captured["aws_access_key_id"] == "test-access"
    assert captured["aws_secret_access_key"] == "test-secret"


def test_s3_signed_url_uses_browser_accessible_origin(monkeypatch) -> None:
    class Client:
        def generate_presigned_url(self, *_args, **_kwargs):
            return (
                "http://minio:9000/digital-human/tenant/avatar.png"
                "?AWSAccessKeyId=test&Signature=signed&Expires=123"
            )

    monkeypatch.setattr(
        boto3,
        "client",
        lambda *_args, **_kwargs: Client(),
    )
    monkeypatch.setattr(
        "app.saas.storage.saas_settings",
        SimpleNamespace(
            storage_bucket="digital-human",
            storage_endpoint="http://minio:9000",
            storage_region=None,
            storage_signed_url_seconds=3600,
            storage_public_base_url="http://192.168.1.234:9005",
        ),
    )

    url = S3ObjectStore().signed_get_url("tenant/avatar.png")

    assert url == (
        "http://192.168.1.234:9005/digital-human/tenant/avatar.png"
        "?AWSAccessKeyId=test&Signature=signed&Expires=123"
    )
