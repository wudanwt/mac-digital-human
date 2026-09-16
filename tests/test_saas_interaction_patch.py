from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.saas.interaction_patch import JS
from app.saas_main import app


def test_interaction_patch_is_served_and_injected() -> None:
    with TestClient(app) as client:
        script = client.get('/interaction-patch.js')
        page = client.get('/')
        assert script.status_code == 200
        assert 'baseDashboard' in script.text
        assert 'bindJobCards' in script.text
        assert 'dataJobDetail' not in script.text
        assert 'dataset.jobDetail' in script.text
        assert 'dataset.jobCardId' in script.text
        assert '/interaction-patch.js' in page.text


@pytest.mark.skipif(shutil.which('node') is None, reason='node required for browser JavaScript syntax check')
def test_interaction_patch_javascript_syntax(tmp_path: Path) -> None:
    script = tmp_path / 'interaction-patch.js'
    script.write_text(JS, encoding='utf-8')
    proc = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
