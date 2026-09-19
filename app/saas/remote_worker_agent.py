from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx


KEYCHAIN_SERVICE = "com.mac-digital-human.remote-worker"
ROOT = Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    override = os.getenv("REMOTE_WORKER_AGENT_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "MacDigitalHumanWorker" / "config.json"


def _is_private_or_local_host(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def validate_center_url(value: str) -> str:
    api_base = value.strip().rstrip("/")
    parsed = urlsplit(api_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Center URL must be an absolute http(s) URL")
    if parsed.scheme == "http" and not _is_private_or_local_host(parsed.hostname):
        raise RuntimeError("Public remote Center endpoints must use HTTPS")
    return api_base


@dataclass(frozen=True)
class AgentRuntime:
    api_base: str
    worker_id: str
    name: str
    token: str


def load_agent_config(path: Path | None = None) -> dict[str, str]:
    target = path or _default_config_path()
    if not target.exists():
        raise RuntimeError(
            f"Remote Worker agent is not enrolled; missing config: {target}"
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Remote Worker agent config is invalid: {target}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Remote Worker agent config is invalid: {target}")
    required = ("api_base", "worker_id", "name")
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise RuntimeError(
            "Remote Worker agent config is missing: " + ", ".join(missing)
        )
    return {key: str(payload[key]).strip() for key in required}


def save_agent_config(payload: dict[str, str], path: Path | None = None) -> Path:
    target = path or _default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.chmod(0o600)
    os.replace(temp, target)
    target.chmod(0o600)
    return target


def _security(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS Keychain is only available on Darwin")
    try:
        return subprocess.run(
            ["security", *args],
            check=check,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("macOS security command was not found") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(message or "macOS Keychain command failed") from exc


def ensure_keychain_available() -> None:
    result = _security(["list-keychains"], check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Keychain is unavailable").strip())


def store_worker_token(worker_id: str, token: str) -> None:
    _security(
        [
            "add-generic-password",
            "-a",
            worker_id,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            token,
            "-U",
        ]
    )


def read_worker_token(worker_id: str) -> str:
    result = _security(
        [
            "find-generic-password",
            "-a",
            worker_id,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ]
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("Remote Worker credential is missing from macOS Keychain")
    return token


def load_agent_runtime(path: Path | None = None) -> AgentRuntime:
    config = load_agent_config(path)
    return AgentRuntime(
        api_base=validate_center_url(config["api_base"]),
        worker_id=config["worker_id"],
        name=config["name"],
        token=read_worker_token(config["worker_id"]),
    )


def enroll(
    *,
    center: str,
    enrollment_code: str,
    name: str,
    config_path: Path | None = None,
) -> AgentRuntime:
    api_base = validate_center_url(center)
    code = enrollment_code.strip()
    if not code:
        raise RuntimeError("Enrollment code is required")
    ensure_keychain_available()
    request_payload = {
        "enrollment_code": code,
        "name": name.strip() or socket.gethostname(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    with httpx.Client(trust_env=False, timeout=30.0) as client:
        response = client.post(f"{api_base}/enroll", json=request_payload)
    if not response.is_success:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text
        raise RuntimeError(f"Center enrollment failed ({response.status_code}): {detail}")

    payload = response.json()
    worker = payload.get("worker") if isinstance(payload, dict) else None
    token = str(payload.get("token") or "") if isinstance(payload, dict) else ""
    worker_id = str((worker or {}).get("id") or "")
    worker_name = str((worker or {}).get("name") or request_payload["name"])
    if not worker_id or not token:
        raise RuntimeError("Center returned an incomplete enrollment response")

    # Persist the secret first. If config persistence fails, the credential is
    # still recoverable from Keychain by worker_id instead of being lost.
    store_worker_token(worker_id, token)
    save_agent_config(
        {
            "api_base": api_base,
            "worker_id": worker_id,
            "name": worker_name,
        },
        config_path,
    )
    return AgentRuntime(
        api_base=api_base,
        worker_id=worker_id,
        name=worker_name,
        token=token,
    )


def install_launch_agent() -> None:
    installer = ROOT / "scripts" / "saas" / "install_distributed_launchagent.py"
    subprocess.run([sys.executable, str(installer), "remote"], check=True)


def _print_status() -> None:
    config = load_agent_config()
    token_available = False
    try:
        token_available = bool(read_worker_token(config["worker_id"]))
    except Exception:
        token_available = False
    print(f"Center API : {config['api_base']}")
    print(f"Worker ID  : {config['worker_id']}")
    print(f"Worker Name: {config['name']}")
    print(f"Credential : {'Keychain ready' if token_available else 'missing'}")


def _print_config_field(field: str) -> None:
    config = load_agent_config()
    if field not in {"api_base", "worker_id", "name"}:
        raise RuntimeError(f"Unsupported config field: {field}")
    print(config[field])


def main() -> None:
    parser = argparse.ArgumentParser(description="Remote Worker enrollment and credential agent")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll_cmd = sub.add_parser("enroll", help="exchange a one-time enrollment code and store the Worker credential in Keychain")
    enroll_cmd.add_argument("--center", required=True, help="Center internal render API base")
    enroll_cmd.add_argument("--code", default="", help="one-time enrollment code; omit to enter it without shell history")
    enroll_cmd.add_argument("--name", default="", help="Worker display name")
    enroll_cmd.add_argument(
        "--install",
        action="store_true",
        help="install/start the user LaunchAgent after successful enrollment",
    )

    sub.add_parser("status", help="show enrolled Center/Worker identity without revealing the credential")

    config_cmd = sub.add_parser("config", help=argparse.SUPPRESS)
    config_cmd.add_argument("--field", required=True, choices=["api_base", "worker_id", "name"])

    args = parser.parse_args()
    try:
        if args.command == "enroll":
            code = args.code or getpass.getpass("Enrollment code: ")
            runtime = enroll(center=args.center, enrollment_code=code, name=args.name)
            print(f"Enrolled Worker: {runtime.name} ({runtime.worker_id})")
            print(f"Center API      : {runtime.api_base}")
            print("Credential      : stored in macOS Keychain")
            if args.install:
                install_launch_agent()
                print("LaunchAgent     : installed and started")
        elif args.command == "status":
            _print_status()
        elif args.command == "config":
            _print_config_field(args.field)
    except RuntimeError as exc:
        print(f"Remote Worker agent error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
