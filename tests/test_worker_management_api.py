from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.saas.worker_management_api import _node_runtime_state


def _node(**overrides):
    values = {
        "last_seen_at": datetime.now(timezone.utc),
        "status": "online",
        "accepting_tasks": True,
        "slots_busy": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_runtime_state_marks_recent_worker_online() -> None:
    state = _node_runtime_state(_node())
    assert state["online"] is True
    assert state["effective_status"] == "online"


def test_runtime_state_prefers_busy_and_draining() -> None:
    busy = _node_runtime_state(_node(slots_busy=1))
    draining = _node_runtime_state(_node(accepting_tasks=False))
    assert busy["effective_status"] == "busy"
    assert draining["effective_status"] == "draining"


def test_runtime_state_marks_stale_worker_offline() -> None:
    state = _node_runtime_state(
        _node(last_seen_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    assert state["online"] is False
    assert state["effective_status"] == "offline"


def test_runtime_state_preserves_terminal_control_states() -> None:
    assert _node_runtime_state(_node(status="revoked"))["effective_status"] == "revoked"
    assert _node_runtime_state(_node(status="incompatible"))["effective_status"] == "incompatible"
    assert _node_runtime_state(_node(status="pending"))["effective_status"] == "pending"
