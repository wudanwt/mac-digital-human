#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROLES = {
    "center": ("com.mac-digital-human.distributed-center", "start_distributed_center.sh"),
    "remote": ("com.mac-digital-human.remote-page-worker", "start_remote_page_worker_mac.sh"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Install a user-level distributed render service")
    parser.add_argument("role", choices=ROLES)
    args = parser.parse_args()

    label, launcher = ROLES[args.role]
    agent_dir = Path.home() / "Library" / "LaunchAgents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    log_dir = ROOT / "workspace"
    log_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agent_dir / f"{label}.plist"
    payload = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", str(ROOT / "scripts" / "saas" / launcher)],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(log_dir / f"{label}.log"),
        "StandardErrorPath": str(log_dir / f"{label}.error.log"),
    }
    with agent_path.open("wb") as fh:
        plistlib.dump(payload, fh)
    agent_path.chmod(0o600)

    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootstrap", domain, str(agent_path)], check=True)
    print(f"Started {label} in {domain}")


if __name__ == "__main__":
    main()
