from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas_main import app


def _register(client: TestClient, prefix: str) -> tuple[str, dict]:
    email = f"{prefix}-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": prefix,
            "workspace_name": f"{prefix} workspace",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data["access_token"], data


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, token: str, name: str, kind: str, content: bytes) -> dict:
    response = client.post(
        "/api/saas/assets",
        headers=_headers(token),
        data={"kind": kind},
        files={"file": (name, BytesIO(content), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _studio_assets(client: TestClient, token: str) -> tuple[dict, dict, dict]:
    return (
        _upload(client, token, "course.pptx", "ppt", b"fake-ppt"),
        _upload(client, token, "master.mp4", "video", b"fake-video"),
        _upload(client, token, "voice.wav", "audio", b"fake-audio"),
    )


def test_health_and_auth_round_trip() -> None:
    with TestClient(app) as client:
        response = client.get("/api/saas/health")
        assert response.status_code == 200, response.text
        assert response.json()["checks"]["database"] == "ok"
        token, registered = _register(client, "auth")
        response = client.get("/api/saas/auth/me", headers=_headers(token))
        assert response.status_code == 200
        me = response.json()
        assert me["user"]["email"] == registered["user"]["email"]
        assert me["workspace"]["role"] == "owner"


def test_full_saas_control_plane_flow_and_tenant_isolation() -> None:
    with TestClient(app) as client:
        token, _ = _register(client, "studio")
        ppt, video, audio = _studio_assets(client, token)

        preview = client.get(f"/api/saas/assets/{ppt['id']}/content", headers=_headers(token))
        assert preview.status_code == 200, preview.text
        assert preview.content == b"fake-ppt"
        assert preview.headers["content-disposition"].startswith("inline;")

        no_consent = client.post(
            "/api/saas/voices",
            headers=_headers(token),
            json={"name": "No consent", "provider": "cosyvoice", "reference_asset_id": audio["id"]},
        )
        assert no_consent.status_code == 422

        voice_response = client.post(
            "/api/saas/voices",
            headers=_headers(token),
            json={
                "name": "Dan Voice",
                "provider": "cosyvoice",
                "reference_asset_id": audio["id"],
                "transcript": "测试音色",
                "consent_confirmed": True,
            },
        )
        assert voice_response.status_code == 201, voice_response.text
        voice = voice_response.json()

        avatar_response = client.post(
            "/api/saas/avatars",
            headers=_headers(token),
            json={
                "name": "Dan Avatar",
                "master_video_asset_id": video["id"],
                "voice_profile_id": voice["id"],
                "consent_confirmed": True,
            },
        )
        assert avatar_response.status_code == 201, avatar_response.text
        avatar = avatar_response.json()

        # Free plan has one avatar; plan limits must be enforced server-side.
        second_avatar = client.post(
            "/api/saas/avatars",
            headers=_headers(token),
            json={
                "name": "Too many",
                "master_video_asset_id": video["id"],
                "consent_confirmed": True,
            },
        )
        assert second_avatar.status_code == 402

        course_response = client.post(
            "/api/saas/courses",
            headers=_headers(token),
            json={
                "title": "SaaS test course",
                "ppt_asset_id": ppt["id"],
                "avatar_id": avatar["id"],
                "voice_profile_id": voice["id"],
                "script": [{"index": 1, "narration": "欢迎来到课程", "layout": "pip"}],
            },
        )
        assert course_response.status_code == 201, course_response.text
        course = course_response.json()

        render_response = client.post(
            f"/api/saas/courses/{course['id']}/render",
            headers=_headers(token),
            json={"engine": "mock", "estimated_seconds": 1, "audio_asset_id": audio["id"]},
        )
        assert render_response.status_code == 202, render_response.text
        job = render_response.json()
        assert job["status"] == "queued"
        assert job["estimated_seconds"] >= 1

        billing = client.get("/api/saas/billing/subscription", headers=_headers(token))
        assert billing.status_code == 200
        assert billing.json()["remaining_minutes"] < 30.0

        cancel = client.post(f"/api/saas/jobs/{job['id']}/cancel", headers=_headers(token))
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["status"] == "canceled"
        after_cancel = client.get("/api/saas/billing/subscription", headers=_headers(token)).json()
        assert after_cancel["remaining_minutes"] == 30.0

        other_token, _ = _register(client, "isolated")
        forbidden_asset = client.get(f"/api/saas/assets/{ppt['id']}", headers=_headers(other_token))
        assert forbidden_asset.status_code == 404
        forbidden_preview = client.get(
            f"/api/saas/assets/{ppt['id']}/content", headers=_headers(other_token)
        )
        assert forbidden_preview.status_code == 404
        forbidden_course = client.get(f"/api/saas/courses/{course['id']}", headers=_headers(other_token))
        assert forbidden_course.status_code == 404


def test_extra_workspace_does_not_mint_more_free_minutes() -> None:
    with TestClient(app) as client:
        token, _ = _register(client, "workspace")
        create = client.post(
            "/api/saas/workspaces",
            headers=_headers(token),
            json={"name": "Second workspace"},
        )
        assert create.status_code == 201, create.text
        second = create.json()
        switched = client.post(
            f"/api/saas/auth/switch-workspace/{second['id']}",
            headers=_headers(token),
        )
        assert switched.status_code == 200, switched.text
        second_token = switched.json()["access_token"]
        subscription = client.get(
            "/api/saas/billing/subscription",
            headers=_headers(second_token),
        ).json()
        assert subscription["remaining_minutes"] == 0.0


def test_billing_plans_and_mock_upgrade_in_development() -> None:
    with TestClient(app) as client:
        token, _ = _register(client, "billing")
        plans = client.get("/api/saas/billing/plans")
        assert plans.status_code == 200
        assert {p["code"] for p in plans.json()} >= {"free", "pro", "business"}
        order = client.post(
            "/api/saas/billing/orders",
            headers=_headers(token),
            json={"plan_code": "pro", "provider": "mock"},
        )
        assert order.status_code == 201, order.text
        assert order.json()["status"] == "paid"
        subscription = client.get("/api/saas/billing/subscription", headers=_headers(token)).json()
        assert subscription["plan_code"] == "pro"
        assert subscription["remaining_minutes"] == 600.0
