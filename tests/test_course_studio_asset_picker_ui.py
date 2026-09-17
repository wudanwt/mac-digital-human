from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.saas.course_studio_asset_picker_ui import CSS, JS


def test_course_picker_uses_composite_digital_human_data() -> None:
    assert "api('/digital-humans')" in JS
    assert "studio-avatar-thumb" in JS
    assert "voice?.name" in JS
    assert "reference_asset?.download_url" in JS
    assert "试听声音" in JS
    assert "master_video_ready" in JS
    assert "voice_ready" in JS
    assert "studio-avatar-choice" in CSS


@pytest.mark.skipif(shutil.which("node") is None, reason="node required for browser JavaScript syntax check")
def test_course_picker_javascript_syntax(tmp_path: Path) -> None:
    script = tmp_path / "course-studio-asset-picker.js"
    script.write_text(JS, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
