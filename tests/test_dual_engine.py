from __future__ import annotations

from app.config import settings
from app.engine import LongCatMLXEngine, MuseTalkMLXEngine
from app.jobs import JobManager


def test_engine_compatibility_exports():
    assert MuseTalkMLXEngine.name == "musetalk"
    assert LongCatMLXEngine.name == "longcat"


def test_m5_pro_defaults():
    assert settings.default_musetalk_variant == "q8"
    assert settings.default_longcat_variant == "q4-merged"
    assert settings.longcat_height == 480
    assert settings.longcat_width == 832
    assert settings.longcat_num_frames == 93
    assert (settings.longcat_num_frames - 1) % 4 == 0


def test_longcat_readiness_contract_without_weights():
    status = LongCatMLXEngine().readiness("q4-merged")
    assert status["engine"] == "longcat"
    assert status["variant"] == "q4-merged"
    assert "checks" in status
    assert "adapter_script" in status["checks"]
    assert "model_dir" in status["checks"]


def test_job_manager_has_both_engines():
    manager = JobManager()
    assert set(manager.engines) == {"musetalk", "longcat"}
