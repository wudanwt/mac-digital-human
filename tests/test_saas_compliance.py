from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas_main import app


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, prefix: str) -> str:
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": f"{prefix}-{uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": prefix,
            "workspace_name": f"{prefix} workspace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _upload(client: TestClient, token: str, name: str, kind: str, content: bytes) -> dict:
    response = client.post(
        "/api/saas/assets",
        headers=_headers(token),
        data={"kind": kind},
        files={"file": (name, BytesIO(content), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_content_report_is_tenant_scoped() -> None:
    with TestClient(app) as client:
        token = _register(client, "report")
        asset = _upload(client, token, "sample.pdf", "document", b"report-target")
        created = client.post(
            "/api/saas/compliance/reports",
            headers=_headers(token),
            json={
                "target_type": "asset",
                "target_id": asset["id"],
                "reason": "rights concern",
                "details": "Please review this file.",
            },
        )
        assert created.status_code == 201, created.text
        reports = client.get("/api/saas/compliance/reports", headers=_headers(token))
        assert reports.status_code == 200
        assert any(item["id"] == created.json()["id"] for item in reports.json())

        other = _register(client, "report-other")
        forbidden = client.post(
            "/api/saas/compliance/reports",
            headers=_headers(other),
            json={"target_type": "asset", "target_id": asset["id"], "reason": "invalid cross tenant"},
        )
        assert forbidden.status_code == 404


def test_avatar_consent_can_be_revoked_and_sources_are_blocked() -> None:
    with TestClient(app) as client:
        token = _register(client, "consent")
        video = _upload(client, token, "master.mp4", "video", b"fake-video")
        avatar = client.post(
            "/api/saas/avatars",
            headers=_headers(token),
            json={"name": "Consent avatar", "master_video_asset_id": video["id"], "consent_confirmed": True},
        )
        assert avatar.status_code == 201, avatar.text
        avatar_id = avatar.json()["id"]

        consents = client.get("/api/saas/compliance/consents", headers=_headers(token))
        assert consents.status_code == 200
        consent = next(item for item in consents.json() if item["subject_id"] == avatar_id)
        revoked = client.post(
            f"/api/saas/compliance/consents/{consent['id']}/revoke",
            headers=_headers(token),
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["revoked_at"] is not None

        avatars = client.get("/api/saas/avatars", headers=_headers(token)).json()
        blocked = next(item for item in avatars if item["id"] == avatar_id)
        assert blocked["status"] == "blocked"
        assert blocked["master_video_asset_id"] is None
