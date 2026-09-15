from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from ..config import settings
from .settings import saas_settings


class ObjectStore(Protocol):
    def put_file(self, source: Path, key: str) -> str: ...


class LocalObjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (settings.outputs_dir / "saas")
        self.root.mkdir(parents=True, exist_ok=True)

    def put_file(self, source: Path, key: str) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target.resolve().as_uri()


class S3ObjectStore:
    """S3-compatible storage for AWS S3, MinIO, OSS gateways and similar services."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional SaaS dependency
            raise RuntimeError("S3 storage requires `pip install .[saas]`") from exc

        self.bucket = saas_settings.storage_bucket
        self.public_base_url = saas_settings.storage_public_base_url
        self.client = boto3.client(
            "s3",
            endpoint_url=saas_settings.storage_endpoint,
            region_name=saas_settings.storage_region,
        )

    def put_file(self, source: Path, key: str) -> str:
        self.client.upload_file(str(source), self.bucket, key)
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{key.lstrip('/')}"
        endpoint = saas_settings.storage_endpoint
        if endpoint:
            return f"{endpoint.rstrip('/')}/{self.bucket}/{key.lstrip('/')}"
        return f"s3://{self.bucket}/{key}"


def build_object_store() -> ObjectStore:
    if saas_settings.storage_backend.lower() in {"s3", "oss", "cos", "minio"}:
        return S3ObjectStore()
    return LocalObjectStore()


object_store = build_object_store()
