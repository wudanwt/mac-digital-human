from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.saas.voice_clone_guard_ui import JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node required for browser JavaScript syntax check")
def test_voice_clone_guard_javascript_syntax(tmp_path: Path) -> None:
    script = tmp_path / "voice-clone-guard.js"
    script.write_text(JS, encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_voice_clone_guard_uses_fixed_exact_prompt() -> None:
    assert "大家好，欢迎来到今天的课程，很高兴和大家一起学习。" in JS
    assert "readOnly = true" in JS
    assert "逐字朗读" in JS
