#!/usr/bin/env python3
from __future__ import annotations

import platform
import shutil
import subprocess
import sys


def cmd_version(name: str, args: list[str]) -> str | None:
    path = shutil.which(name)
    if not path:
        return None
    try:
        out = subprocess.check_output([path, *args], stderr=subprocess.STDOUT, text=True, timeout=5)
        return out.splitlines()[0] if out else path
    except Exception:
        return path


def main() -> int:
    print("Mac Digital Human - 环境检查")
    print(f"OS: {platform.platform()}")
    print(f"Machine: {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")

    ok = True
    if sys.platform != "darwin":
        print("[WARN] 当前不是 macOS，本项目第一目标平台是 Apple Silicon Mac")
    if platform.machine() != "arm64":
        print("[FAIL] 当前不是 arm64 Apple Silicon")
        ok = False
    if sys.version_info < (3, 11):
        print("[WARN] 推荐 Python 3.11；setup.sh 会由 uv 创建 3.11 环境")

    for name, args in [("git", ["--version"]), ("ffmpeg", ["-version"]), ("uv", ["--version"]), ("brew", ["--version"])]:
        version = cmd_version(name, args)
        print(f"{name}: {version or 'NOT FOUND'}")
        if name in {"git", "ffmpeg", "uv"} and not version:
            ok = False

    try:
        mem = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        print(f"Memory: {int(mem) / 1024**3:.1f} GB")
    except Exception:
        pass

    print("\n结果:", "基础环境可用" if ok else "需要先运行 bash scripts/setup.sh")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
