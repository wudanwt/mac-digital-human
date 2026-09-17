from __future__ import annotations

from pathlib import Path

from app.saas.remote_page_worker import RemoteApi, RemoteWorkerConfig


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
