from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.saas.job_detail_ui import JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node required for browser JavaScript syntax check")
def test_job_detail_javascript_syntax(tmp_path: Path) -> None:
    script = tmp_path / "job-detail.js"
    script.write_text(JS, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
