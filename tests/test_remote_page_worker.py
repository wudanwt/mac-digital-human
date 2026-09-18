from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.saas import mlx_preflight
from app.saas.remote_page_worker import RemoteApi, RemoteWorkerConfig, worker_instance_lock


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


def test_remote_api_resolves_task_scoped_relative_urls(tmp_path: Path) -> None:
    api = RemoteApi(_config(tmp_path))
    try:
        assert api._resource_url("/api/saas/internal/render/tasks/t1/assets/a1") == (
            "http://192.168.1.10:8918/api/saas/internal/render/tasks/t1/assets/a1"
        )
        assert api._resource_url("https://files.example.test/object") == "https://files.example.test/object"
    finally:
        api.close()


def test_remote_worker_rejects_duplicate_process_for_same_cache(tmp_path: Path) -> None:
    with worker_instance_lock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with worker_instance_lock(tmp_path):
                pass

    with worker_instance_lock(tmp_path):
        assert (tmp_path / ".remote-page-worker.lock").read_text().strip()


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
