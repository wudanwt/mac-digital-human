from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.saas import mlx_preflight
from app.saas.remote_page_worker import RemoteApi, RemoteWorkerConfig, worker_instance_lock, worker_lock_path


def _config(tmp_path: Path) -> RemoteWorkerConfig:
    return RemoteWorkerConfig(
        api_base="http://192.168.1.10:8918/api/saas/internal/render",
        token="test-worker-token",
        name="mini-test",
        code_version="0.5.0",
        model_version="musetalk-mlx",
        render_contract_version="v1",
        cache_dir=tmp_path,
        cache_limit_bytes=20 * 1024**3,
        min_disk_free_bytes=10 * 1024**3,
        transfer_slots=2,
        upload_chunk_bytes=8 * 1024**2,
        request_timeout_seconds=30.0,
    )


def test_remote_api_rejects_public_plain_http(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("REMOTE_WORKER_ALLOW_INSECURE_HTTP", raising=False)
    config = replace(
        _config(tmp_path),
        api_base="http://worker-api.example.com/api/saas/internal/render",
    )
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        RemoteApi(config)


def test_remote_api_accepts_public_https(tmp_path: Path) -> None:
    config = replace(
        _config(tmp_path),
        api_base="https://worker-api.example.com/api/saas/internal/render",
    )
    api = RemoteApi(config)
    api.close()


def test_remote_api_resolves_task_scoped_relative_urls(tmp_path: Path) -> None:
    api = RemoteApi(_config(tmp_path))
    try:
        assert api._resource_url("/api/saas/internal/render/tasks/t1/assets/a1") == (
            "http://192.168.1.10:8918/api/saas/internal/render/tasks/t1/assets/a1"
        )
        assert api._resource_url("https://files.example.test/object") == "https://files.example.test/object"
    finally:
        api.close()




def test_public_plain_http_direct_download_uses_center_fallback(tmp_path: Path) -> None:
    api = RemoteApi(_config(tmp_path))
    try:
        task = {"id": "task-1", "attempt_id": "attempt-1", "lease_token": "lease-secret"}
        candidates = api._download_candidates(
            task,
            {
                "id": "asset-1",
                "transfer_mode": "direct",
                "url": "http://objects.example.test/private/asset?signature=abc",
                "fallback_url": "/api/saas/internal/render/tasks/task-1/assets/asset-1",
            },
        )
        assert len(candidates) == 1
        mode, client, url, headers = candidates[0]
        assert mode == "proxy"
        assert client is api.control_client
        assert url == "http://192.168.1.10:8918/api/saas/internal/render/tasks/task-1/assets/asset-1"
        assert headers["X-Attempt-Id"] == "attempt-1"
        assert headers["X-Lease-Token"] == "lease-secret"
    finally:
        api.close()


def test_direct_download_never_sends_worker_credentials_to_object_store(tmp_path: Path) -> None:
    api = RemoteApi(_config(tmp_path))
    payload = b"signed-object-payload"
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, content=payload, request=request)

    api.transfer_client.close()
    api.transfer_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        destination = tmp_path / "downloaded.bin"
        result = api.download(
            {"id": "task-1", "attempt_id": "attempt-1", "lease_token": "lease-secret"},
            {
                "id": "asset-1",
                "transfer_mode": "direct",
                "url": "https://objects.example.test/private/asset?signature=abc",
                "fallback_url": "/api/saas/internal/render/tasks/task-1/assets/asset-1",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            destination,
        )
        assert result.read_bytes() == payload
        assert "authorization" not in seen_headers
        assert "x-attempt-id" not in seen_headers
        assert "x-lease-token" not in seen_headers
    finally:
        api.close()


def test_direct_download_falls_back_to_authenticated_center_proxy(tmp_path: Path) -> None:
    api = RemoteApi(_config(tmp_path))
    payload = b"center-fallback"
    direct_calls = 0
    proxy_headers: dict[str, str] = {}

    def direct_handler(request: httpx.Request) -> httpx.Response:
        nonlocal direct_calls
        direct_calls += 1
        return httpx.Response(403, request=request)

    def proxy_handler(request: httpx.Request) -> httpx.Response:
        proxy_headers.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, content=payload, request=request)

    api.transfer_client.close()
    api.control_client.close()
    api.transfer_client = httpx.Client(transport=httpx.MockTransport(direct_handler), trust_env=False)
    api.control_client = httpx.Client(
        base_url=api.origin,
        headers={"Authorization": "Bearer test-worker-token"},
        transport=httpx.MockTransport(proxy_handler),
        trust_env=False,
    )
    try:
        destination = tmp_path / "fallback.bin"
        result = api.download(
            {"id": "task-1", "attempt_id": "attempt-1", "lease_token": "lease-secret"},
            {
                "id": "asset-1",
                "transfer_mode": "direct",
                "url": "https://objects.example.test/private/expired?signature=abc",
                "fallback_url": "/api/saas/internal/render/tasks/task-1/assets/asset-1",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            destination,
        )
        assert result.read_bytes() == payload
        assert direct_calls == 1
        assert proxy_headers["authorization"] == "Bearer test-worker-token"
        assert proxy_headers["x-attempt-id"] == "attempt-1"
        assert proxy_headers["x-lease-token"] == "lease-secret"
    finally:
        api.close()


def test_remote_worker_rejects_duplicate_process_for_same_cache(tmp_path: Path) -> None:
    lock_path = worker_lock_path(tmp_path)
    assert lock_path.parent == tmp_path.resolve().parent / ".remote-worker-locks"
    assert tmp_path.resolve() not in lock_path.parents

    with worker_instance_lock(tmp_path):
        assert lock_path.read_text().strip()
        with pytest.raises(RuntimeError, match="already running"):
            with worker_instance_lock(tmp_path):
                pass

    with worker_instance_lock(tmp_path):
        assert lock_path.read_text().strip()


def test_remote_preflight_uses_center_api_without_local_services(monkeypatch) -> None:
    monkeypatch.setattr(mlx_preflight.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mlx_preflight.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(mlx_preflight.shutil, "which", lambda command: "/usr/bin/ffmpeg")
    monkeypatch.setattr(mlx_preflight.MuseTalkMLXEngine, "readiness", lambda self: {"ready": True})
    monkeypatch.setattr(mlx_preflight.CosyVoiceTTS, "readiness", lambda self: {"ready": True})
    monkeypatch.setattr(mlx_preflight.PortraitMattingEngine, "readiness", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(mlx_preflight.object_store, "healthcheck", lambda: (_ for _ in ()).throw(AssertionError()))

    urls = []

    class Client:
        def __init__(self, *, trust_env, timeout):
            assert trust_env is False
            assert timeout == 5.0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url):
            urls.append(url)
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(mlx_preflight.httpx, "Client", Client)
    result = mlx_preflight.collect("http://center:8918/api/saas/internal/render")
    assert result["ready"] is True
    assert urls == ["http://center:8918/api/saas/health"]
    assert "database" not in result["checks"]
    assert "portrait_matting" not in result["checks"]


def test_remote_preflight_rejects_invalid_center_url(monkeypatch) -> None:
    monkeypatch.setattr(mlx_preflight.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mlx_preflight.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(mlx_preflight.shutil, "which", lambda command: "/usr/bin/ffmpeg")
    monkeypatch.setattr(mlx_preflight.MuseTalkMLXEngine, "readiness", lambda self: {"ready": True})
    monkeypatch.setattr(mlx_preflight.CosyVoiceTTS, "readiness", lambda self: {"ready": True})
    result = mlx_preflight.collect("not-a-url")
    assert result["ready"] is False
    assert result["checks"]["center_api"]["ready"] is False
