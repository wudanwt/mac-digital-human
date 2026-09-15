from __future__ import annotations

from app.config import settings
from app.engines import MuseTalkMLXEngine
from app.jobs import JobManager


def test_engine_compatibility_exports():
    assert MuseTalkMLXEngine.name == "musetalk"


def test_m5_pro_defaults():
    assert settings.default_musetalk_variant == "q8"
    assert settings.musetalk_target_fps == 25


def test_musetalk_readiness_contract():
    status = MuseTalkMLXEngine().readiness("q8")
    assert status["engine"] == "musetalk"
    assert status["variant"] == "q8"
    assert "checks" in status


def test_job_manager_has_musetalk_engine():
    manager = JobManager()
    assert "musetalk" in manager.engines

