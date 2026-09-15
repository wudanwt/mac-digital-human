#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

from app.composer import media_duration
from app.config import settings


def _system_profiler() -> dict:
    if platform.system() != "Darwin":
        return {}
    try:
        proc = subprocess.run(
            ["system_profiler", "SPHardwareDataType", "-json"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        rows = payload.get("SPHardwareDataType", [])
        return rows[0] if rows else {}
    except Exception:
        return {}


def _peak_tree_rss(proc: psutil.Process) -> int:
    total = 0
    try:
        total += proc.memory_info().rss
    except psutil.Error:
        pass
    try:
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an avatar render and record real-machine performance")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--variant", default="q8")
    parser.add_argument("--label", default="first-run")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bench_dir = settings.root / "benchmarks" / "local"
    bench_dir.mkdir(parents=True, exist_ok=True)
    output = bench_dir / f"{stamp}-musetalk.mp4"
    report_path = bench_dir / f"{stamp}-musetalk.json"

    cmd = [
        sys.executable,
        "-m",
        "app.cli",
        "--audio",
        str(args.audio),
        "--video",
        str(args.video),
        "--variant",
        args.variant,
        "--output",
        str(output),
    ]

    vm_before = psutil.virtual_memory()
    started = time.time()
    child = subprocess.Popen(cmd, cwd=settings.root)
    process = psutil.Process(child.pid)
    peak_rss = 0
    min_available = vm_before.available
    while child.poll() is None:
        peak_rss = max(peak_rss, _peak_tree_rss(process))
        min_available = min(min_available, psutil.virtual_memory().available)
        time.sleep(0.25)
    elapsed = time.time() - started
    peak_rss = max(peak_rss, _peak_tree_rss(process))

    duration = media_duration(output) if child.returncode == 0 and output.exists() else None
    hardware = _system_profiler()
    report = {
        "label": args.label,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "engine": "musetalk",
        "variant": args.variant,
        "command": cmd,
        "exit_code": child.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "output": str(output) if output.exists() else None,
        "output_duration_seconds": round(duration, 3) if duration else None,
        "realtime_factor": round(elapsed / duration, 3) if duration else None,
        "peak_process_tree_rss_gb": round(peak_rss / (1024 ** 3), 3),
        "system_memory_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 3),
        "minimum_available_memory_gb": round(min_available / (1024 ** 3), 3),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hardware": {
            "machine_name": hardware.get("machine_name"),
            "machine_model": hardware.get("machine_model"),
            "chip_type": hardware.get("chip_type"),
            "number_processors": hardware.get("number_processors"),
            "physical_memory": hardware.get("physical_memory"),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nBenchmark report: {report_path}")
    return int(child.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())

