from __future__ import annotations

from app.saas.worker_status_api import merge_engine_status
from app.saas.worker_ui import JS


def test_merge_engine_status_uses_distributed_mac_workers() -> None:
    engines = {
        "mock": {"online": True, "count": 1},
        "musetalk": {"online": True, "count": 1},
    }
    nodes = [
        {"online": True, "status": "online"},
        {"online": True, "status": "busy"},
        {"online": False, "status": "offline"},
    ]
    merged = merge_engine_status(engines, nodes, distributed_enabled=True)
    assert merged["mock"]["count"] == 1
    assert merged["musetalk"]["count"] == 2
    assert merged["musetalk"]["registered"] == 3
    assert merged["musetalk"]["online"] is True


def test_merge_engine_status_ignores_distributed_when_disabled() -> None:
    engines = {"musetalk": {"online": True, "count": 1}}
    nodes = [{"online": True, "status": "online"}] * 3
    merged = merge_engine_status(engines, nodes, distributed_enabled=False)
    assert merged["musetalk"]["count"] == 1
    assert "registered" not in merged["musetalk"]


def test_worker_ui_reads_distributed_mac_worker_counts() -> None:
    assert "engineInfo(status,radio.value)" in JS
    assert "dist.online_count" in JS
    assert "dist.registered_count" in JS
    assert "台" in JS
    assert "status.engines?.[engine]" in JS
