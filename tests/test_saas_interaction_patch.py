from fastapi.testclient import TestClient

from app.saas_main import app


def test_interaction_patch_is_served_and_injected() -> None:
    with TestClient(app) as client:
        script = client.get('/interaction-patch.js')
        page = client.get('/')
        assert script.status_code == 200
        assert 'baseDashboard' in script.text
        assert '/interaction-patch.js' in page.text
