from __future__ import annotations

import time
from types import SimpleNamespace
import pytest

from app.saas.remote_page_worker import LeaseKeeper, LeaseLost, RemoteApiError


def test_lease_keeper_normal_renewal() -> None:
    calls = []

    def mock_renew(task: dict) -> str:
        calls.append(task["id"])
        return "2026-09-20T21:00:00Z"

    api = SimpleNamespace(renew=mock_renew)
    task = {"id": "task-test-1"}

    with LeaseKeeper(api, task, interval=0) as lease:
        time.sleep(0.05)
        lease.checkpoint()

    assert len(calls) >= 1


def test_lease_keeper_recovers_from_transient_error() -> None:
    call_count = 0

    def mock_renew(task: dict) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporary network timeout")
        return "2026-09-20T21:00:00Z"

    api = SimpleNamespace(renew=mock_renew)
    task = {"id": "task-test-2"}

    # Set interval very small for test speed
    with LeaseKeeper(api, task, interval=0, grace_period_seconds=5.0) as lease:
        time.sleep(0.08)
        # Should not raise LeaseLost because it recovers on subsequent attempts
        lease.checkpoint()

    assert call_count >= 2


def test_lease_keeper_conflict_triggers_immediate_loss() -> None:
    def mock_renew(task: dict) -> str:
        raise RemoteApiError("Conflict: task lease expired or reclaimed", status_code=409)

    api = SimpleNamespace(renew=mock_renew)
    task = {"id": "task-test-3"}

    with LeaseKeeper(api, task, interval=0, grace_period_seconds=100.0) as lease:
        time.sleep(0.05)
        with pytest.raises(LeaseLost):
            lease.checkpoint()


def test_lease_keeper_grace_period_expiry() -> None:
    def mock_renew(task: dict) -> str:
        raise RuntimeError("Persistent network outage")

    api = SimpleNamespace(renew=mock_renew)
    task = {"id": "task-test-4"}

    # Set a tiny grace period to test expiration
    with LeaseKeeper(api, task, interval=0, grace_period_seconds=0.02) as lease:
        time.sleep(0.06)
        with pytest.raises(LeaseLost):
            lease.checkpoint()
