from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.saas import remote_worker_agent
from app.saas.remote_page_worker import RemoteWorkerConfig


def test_agent_config_contains_no_secret_and_is_private(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    remote_worker_agent.save_agent_config(
        {
            "api_base": "https://worker-api.example.com/api/saas/internal/render",
            "worker_id": "worker-1",
            "name": "remote-mini",
        },
        path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "api_base": "https://worker-api.example.com/api/saas/internal/render",
        "worker_id": "worker-1",
        "name": "remote-mini",
    }
    assert "token" not in payload
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_agent_enrollment_stores_token_in_keychain_only(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "agent-config.json"
    stored: dict[str, str] = {}
    monkeypatch.setattr(remote_worker_agent, "ensure_keychain_available", lambda: None)
    monkeypatch.setattr(
        remote_worker_agent,
        "store_worker_token",
        lambda worker_id, token: stored.update(worker_id=worker_id, token=token),
    )
    monkeypatch.setattr(remote_worker_agent.socket, "gethostname", lambda: "test-mini.local")
    monkeypatch.setattr(remote_worker_agent.platform, "platform", lambda: "macOS-test")
    monkeypatch.setattr(remote_worker_agent.platform, "machine", lambda: "arm64")

    class Client:
        def __init__(self, *, trust_env, timeout):
            assert trust_env is False
            assert timeout == 30.0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            assert url == "https://worker-api.example.com/api/saas/internal/render/enroll"
            assert json["enrollment_code"] == "enr_test_secret"
            return httpx.Response(
                200,
                json={
                    "worker": {"id": "node-1", "name": "remote-mini"},
                    "token": "wrk_node-1_super-secret",
                },
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(remote_worker_agent.httpx, "Client", Client)
    runtime = remote_worker_agent.enroll(
        center="https://worker-api.example.com/api/saas/internal/render",
        enrollment_code="enr_test_secret",
        name="remote-mini",
        config_path=config_path,
    )
    assert runtime.worker_id == "node-1"
    assert stored == {"worker_id": "node-1", "token": "wrk_node-1_super-secret"}
    raw = config_path.read_text(encoding="utf-8")
    assert "wrk_node-1_super-secret" not in raw
    assert "enr_test_secret" not in raw


def test_keychain_uses_worker_id_as_account(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(remote_worker_agent.platform, "system", lambda: "Darwin")

    def run(args, *, check, capture_output, text):
        calls.append(args)
        if "find-generic-password" in args:
            return SimpleNamespace(returncode=0, stdout="wrk_secret\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(remote_worker_agent.subprocess, "run", run)
    remote_worker_agent.store_worker_token("node-123", "wrk_secret")
    assert remote_worker_agent.read_worker_token("node-123") == "wrk_secret"
    assert calls[0][0] == "security"
    assert remote_worker_agent.KEYCHAIN_SERVICE in calls[0]
    assert "node-123" in calls[0]


def test_remote_worker_config_falls_back_to_enrolled_keychain_runtime(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("REMOTE_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("REMOTE_WORKER_API_BASE", raising=False)
    monkeypatch.delenv("REMOTE_WORKER_NAME", raising=False)
    monkeypatch.setenv("REMOTE_WORKER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        remote_worker_agent,
        "load_agent_runtime",
        lambda: remote_worker_agent.AgentRuntime(
            api_base="https://worker-api.example.com/api/saas/internal/render",
            worker_id="node-1",
            name="keychain-mini",
            token="wrk_keychain_secret",
        ),
    )
    config = RemoteWorkerConfig.from_env()
    assert config.api_base == "https://worker-api.example.com/api/saas/internal/render"
    assert config.name == "keychain-mini"
    assert config.token == "wrk_keychain_secret"


def test_agent_rejects_public_plain_http_center() -> None:
    with pytest.raises(RuntimeError, match="must use HTTPS"):
        remote_worker_agent.validate_center_url(
            "http://worker-api.example.com/api/saas/internal/render"
        )
    assert remote_worker_agent.validate_center_url(
        "http://192.168.1.10:8918/api/saas/internal/render"
    ).startswith("http://192.168.1.10")


def test_install_launch_agent_uses_current_python(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def run(args, *, check):
        calls.append((args, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(remote_worker_agent.subprocess, "run", run)
    remote_worker_agent.install_launch_agent()
    args, check = calls[0]
    assert args[0] == remote_worker_agent.sys.executable
    assert args[-1] == "remote"
    assert check is True


def test_remote_worker_config_keeps_legacy_env_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "REMOTE_WORKER_API_BASE",
        "https://legacy-worker-api.example.com/api/saas/internal/render",
    )
    monkeypatch.setenv("REMOTE_WORKER_TOKEN", "wrk_legacy_secret")
    monkeypatch.setenv("REMOTE_WORKER_NAME", "legacy-mini")
    monkeypatch.setenv("REMOTE_WORKER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        remote_worker_agent,
        "load_agent_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("Keychain should not be read")),
    )
    config = RemoteWorkerConfig.from_env()
    assert config.api_base == "https://legacy-worker-api.example.com/api/saas/internal/render"
    assert config.token == "wrk_legacy_secret"
    assert config.name == "legacy-mini"
