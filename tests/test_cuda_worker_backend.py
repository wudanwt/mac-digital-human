from __future__ import annotations

from app.engines.factory import create_musetalk_engine, normalize_musetalk_backend
from app.engines.musetalk import MuseTalkMLXEngine
from app.engines.musetalk_cuda import MuseTalkCUDAEngine
from app.saas.distributed_worker_api import WorkerRegisterRequest, _compatibility_error
from app.saas.remote_page_worker import RemoteWorkerConfig
from app.saas.settings import saas_settings


def test_mlx_remains_default_backend(monkeypatch):
    monkeypatch.delenv("REMOTE_WORKER_RENDER_BACKEND", raising=False)
    assert normalize_musetalk_backend() == "mlx"
    assert isinstance(create_musetalk_engine(), MuseTalkMLXEngine)


def test_cuda_backend_is_explicit_and_isolated():
    assert normalize_musetalk_backend("cuda") == "cuda"
    assert isinstance(create_musetalk_engine("cuda"), MuseTalkCUDAEngine)


def test_cuda_remote_config_gets_cuda_model_default(monkeypatch, tmp_path):
    monkeypatch.setenv("REMOTE_WORKER_RENDER_BACKEND", "cuda")
    monkeypatch.setenv("REMOTE_WORKER_TOKEN", "test-worker-token")
    monkeypatch.setenv(
        "REMOTE_WORKER_API_BASE",
        "https://worker-api.example.com/api/saas/internal/render",
    )
    monkeypatch.setenv("REMOTE_WORKER_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("REMOTE_WORKER_MODEL_VERSION", raising=False)

    config = RemoteWorkerConfig.from_env()

    assert config.render_backend == "cuda"
    assert config.model_version == "musetalk-cuda"


def test_model_gate_accepts_mlx_and_cuda(monkeypatch):
    original = saas_settings.distributed_expected_model_version
    object.__setattr__(
        saas_settings,
        "distributed_expected_model_version",
        "musetalk-mlx,musetalk-cuda",
    )
    try:
        for model_version in ("musetalk-mlx", "musetalk-cuda"):
            body = WorkerRegisterRequest(
                name="worker",
                host="worker.local",
                platform="test",
                machine="test",
                slots_total=1,
                capabilities=["musetalk"],
                versions={},
                code_version=saas_settings.distributed_expected_code_version,
                model_version=model_version,
                render_contract_version=saas_settings.render_contract_version,
            )
            assert _compatibility_error(body) is None
    finally:
        object.__setattr__(
            saas_settings,
            "distributed_expected_model_version",
            original,
        )
