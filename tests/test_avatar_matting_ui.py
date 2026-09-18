from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.saas.avatar_matting_ui import JS


def test_avatar_matting_ui_contains_asset_controls(tmp_path: Path) -> None:
    assert "/avatar-matting/" in JS
    assert "生成透明资产" in JS
    assert "透明预览" in JS
    assert "白底预览" in JS
    assert "重新抠像" in JS
    assert "document.addEventListener('click'" in JS
    assert "data-dh-matte-state" in JS
    assert "record.addedNodes" in JS
    assert "},1200)" in JS

    node = shutil.which("node")
    if node:
        script = tmp_path / "avatar-matting.js"
        script.write_text(JS, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
