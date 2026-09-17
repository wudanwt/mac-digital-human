from __future__ import annotations

from fastapi.testclient import TestClient

from app.saas_main import app


def test_course_picker_assets_are_served_and_injected() -> None:
    with TestClient(app) as client:
        css = client.get('/course-studio-asset-picker.css')
        js = client.get('/course-studio-asset-picker.js')
        page = client.get('/')
        assert css.status_code == 200
        assert js.status_code == 200
        assert 'studio-avatar-choice' in css.text
        assert "api('/digital-humans')" in js.text
        assert '/course-studio-asset-picker.css' in page.text
        assert '/course-studio-asset-picker.js' in page.text
