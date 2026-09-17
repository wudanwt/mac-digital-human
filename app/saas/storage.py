from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import uuid4

from .settings import saas_settings


class ObjectStore(Protocol):
    def put_file(self, source: Path, key: str) -> str: ...
    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str: ...
    def materialize(self, key: str, destination: Path) -> Path: ...
    def delete(self, key: str) -> None: ...
    def signed_get_url(self, key: str) -> str | None: ...
    def local_path(self, key: str) -> Path | None: ...
    def healthcheck(self) -> None: ...


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

    @staticmethod
    def _temporary_target(target: Path) -> Path:
        return target.with_name(f".{target.name}.{uuid4().hex}.part")

    @staticmethod
    def _commit_file(temp: Path, target: Path) -> None:
        # temp and target deliberately share a directory/filesystem, so replace is
        # atomic: readers see either the previous complete object or the newly
        # verified complete object, never a partial copy.
        os.replace(temp, target)

    def put_file(self, source: Path, key: str) -> str:
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = self._temporary_target(target)
        try:
            shutil.copy2(source, temp)
            self._commit_file(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return f"local://{key}"

    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str:
        del content_type
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = self._temporary_target(target)
        try:
            with temp.open("wb") as out:
                shutil.copyfileobj(stream, out, length=1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            self._commit_file(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return f"local://{key}"

    def materialize(self, key: str, destination: Path) -> Path:
        source = self._target(key)
        if not source.exists():
            raise FileNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return destination

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

    def healthcheck(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / ".healthcheck"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)


class S3ObjectStore:
    """Private AWS S3 or S3-compatible MinIO storage."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("S3 storage requires `pip install .[saas]`") from exc
        self.bucket = saas_settings.storage_bucket
        if not self.bucket:
            raise RuntimeError("STORAGE_BUCKET is required")
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

    def materialize(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))
        return destination

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

    def healthcheck(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


class OSSObjectStore:
    """Alibaba Cloud OSS private-bucket adapter."""

    def __init__(self) -> None:
        try:
            import oss2
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("OSS storage requires `pip install .[saas]`") from exc
        endpoint = saas_settings.storage_endpoint
        access_key_id = os.getenv("OSS_ACCESS_KEY_ID") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        if not endpoint or not access_key_id or not access_key_secret or not saas_settings.storage_bucket:
            raise RuntimeError(
                "OSS requires STORAGE_ENDPOINT, STORAGE_BUCKET, OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET"
            )
        self._oss2 = oss2
        self.bucket_name = saas_settings.storage_bucket
        self.bucket = oss2.Bucket(oss2.Auth(access_key_id, access_key_secret), endpoint, self.bucket_name)

    def put_file(self, source: Path, key: str) -> str:
        self.bucket.put_object_from_file(key, str(source))
        return f"oss://{self.bucket_name}/{key}"

    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str:
        headers = {"Content-Type": content_type} if content_type else None
        self.bucket.put_object(key, stream, headers=headers)
        return f"oss://{self.bucket_name}/{key}"

    def materialize(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.bucket.get_object_to_file(key, str(destination))
        return destination

    def delete(self, key: str) -> None:
        self.bucket.delete_object(key)

    def signed_get_url(self, key: str) -> str | None:
        return self.bucket.sign_url("GET", key, saas_settings.storage_signed_url_seconds)

    def local_path(self, key: str) -> Path | None:
        del key
        return None

    def healthcheck(self) -> None:
        self.bucket.get_bucket_info()


class COSObjectStore:
    """Tencent Cloud COS private-bucket adapter."""

    def __init__(self) -> None:
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("COS storage requires `pip install .[saas]`") from exc
        secret_id = os.getenv("COS_SECRET_ID") or os.getenv("TENCENTCLOUD_SECRET_ID")
        secret_key = os.getenv("COS_SECRET_KEY") or os.getenv("TENCENTCLOUD_SECRET_KEY")
        region = saas_settings.storage_region
        if not secret_id or not secret_key or not region or not saas_settings.storage_bucket:
            raise RuntimeError("COS requires STORAGE_BUCKET, STORAGE_REGION, COS_SECRET_ID and COS_SECRET_KEY")
        self.bucket = saas_settings.storage_bucket
        self.client = CosS3Client(CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Scheme="https"))

    def put_file(self, source: Path, key: str) -> str:
        self.client.upload_file(Bucket=self.bucket, LocalFilePath=str(source), Key=key, EnableMD5=False)
        return f"cos://{self.bucket}/{key}"

    def put_stream(self, stream: BinaryIO, key: str, content_type: str | None = None) -> str:
        kwargs = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Body=stream, Key=key, **kwargs)
        return f"cos://{self.bucket}/{key}"

    def materialize(self, key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        response["Body"].get_stream_to_file(str(destination))
        return destination

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_get_url(self, key: str) -> str | None:
        return self.client.get_presigned_url(
            Method="GET",
            Bucket=self.bucket,
            Key=key,
            Expired=saas_settings.storage_signed_url_seconds,
        )

    def local_path(self, key: str) -> Path | None:
        del key
        return None

    def healthcheck(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)


def build_object_store() -> ObjectStore:
    backend = saas_settings.storage_backend.lower().strip()
    if backend == "local":
        return LocalObjectStore()
    if backend in {"s3", "minio"}:
        return S3ObjectStore()
    if backend == "oss":
        return OSSObjectStore()
    if backend == "cos":
        return COSObjectStore()
    raise RuntimeError(f"Unsupported STORAGE_BACKEND: {backend}")


object_store = build_object_store()
