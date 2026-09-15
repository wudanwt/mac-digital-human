from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from .settings import saas_settings


class ObjectStore(Protocol):
    def put_file(self, source: Path, key: str) -> str: ...
    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str: ...
    def delete(self, key: str) -> None: ...
    def signed_get_url(self, key: str) -> str | None: ...
    def local_path(self, key: str) -> Path | None: ...


class LocalObjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or saas_settings.storage_local_root
        self.root.mkdir(parents=True, exist_ok=True)

    def _target(self, key: str) -> Path:
        target = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in target.parents and target != root:
            raise ValueError("invalid object key")
        return target

    def put_file(self, source: Path, key: str) -> str:
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return f"local://{key}"

    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str:
        del content_type
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            shutil.copyfileobj(stream, out, length=1024 * 1024)
        return f"local://{key}"

    def delete(self, key: str) -> None:
        path = self._target(key)
        if path.exists():
            path.unlink()

    def signed_get_url(self, key: str) -> str | None:
        del key
        return None

    def local_path(self, key: str) -> Path | None:
        path = self._target(key)
        return path if path.exists() else None


class S3ObjectStore:
    """Private S3-compatible storage for S3/MinIO and compatible OSS/COS gateways."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("S3 storage requires `pip install .[saas]`") from exc

        self.bucket = saas_settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=saas_settings.storage_endpoint,
            region_name=saas_settings.storage_region,
        )

    def put_file(self, source: Path, key: str) -> str:
        self.client.upload_file(str(source), self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else None
        kwargs = {"ExtraArgs": extra} if extra else {}
        self.client.upload_fileobj(stream, self.bucket, key, **kwargs)
        return f"s3://{self.bucket}/{key}"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_get_url(self, key: str) -> str | None:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=saas_settings.storage_signed_url_seconds,
        )

    def local_path(self, key: str) -> Path | None:
        del key
        return None


def build_object_store() -> ObjectStore:
    if saas_settings.storage_backend.lower() in {"s3", "oss", "cos", "minio"}:
        return S3ObjectStore()
    return LocalObjectStore()


object_store = build_object_store()
