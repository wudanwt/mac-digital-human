from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.saas.course_avatar_mode_ui import JS


def test_course_avatar_mode_ui_persists_and_previews_modes(tmp_path: Path) -> None:
    assert "avatar_mode" in JS
    assert "transparent" in JS
    assert "white" in JS
    assert "original" in JS
    assert "alph" not in JS.lower()  # browser preview consumes the cutout poster, not mask processing
    assert "/avatar-matting/" in JS
    assert "将当前模式应用到全部页面" in JS
    assert "Number(active.dataset.layoutSlide)+1" in JS
    assert "document.addEventListener('click'" in JS
    assert "section.dataset.avatarModeState===renderKey" in JS
    assert "r.addedNodes" in JS
    assert "section.querySelectorAll('[data-avatar-mode]').forEach" not in JS

    node = shutil.which("node")
    if node:
        script = tmp_path / "course-avatar-mode.js"
        script.write_text(JS, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
