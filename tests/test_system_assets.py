from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas.database import SessionLocal
from app.saas.models import Asset, Avatar
from app.saas.system_assets import publish_template
from app.saas_main import app


def _register(client: TestClient) -> tuple[str, str]:
    result = client.post("/api/saas/auth/register", json={
        "email": f"system-{uuid4().hex}@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "System assets test",
        "workspace_name": f"Workspace {uuid4().hex[:8]}",
    })
    assert result.status_code == 201, result.text
    payload = result.json()
    return payload["access_token"], payload["workspace"]["id"]


def _upload(client: TestClient, token: str, kind: str, name: str, contents: bytes) -> str:
    result = client.post("/api/saas/assets", headers={"Authorization": f"Bearer {token}"},
                         data={"kind": kind}, files={"file": (name, BytesIO(contents), "application/octet-stream")})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_system_catalog_imports_isolated_copies_and_is_idempotent() -> None:
    with TestClient(app) as client:
        source_token, _ = _register(client)
        target_token, target_tenant = _register(client)
        source_headers = {"Authorization": f"Bearer {source_token}"}
        target_headers = {"Authorization": f"Bearer {target_token}"}
        image_id = _upload(client, source_token, "image", "teacher.png", b"image data")
        video_id = _upload(client, source_token, "video", "teacher.mp4", b"video data")
        audio_id = _upload(client, source_token, "audio", "reference.wav", b"audio data")
        background_id = _upload(client, source_token, "background", "stage.png", b"background data")
        voice = client.post("/api/saas/voices", headers=source_headers, json={
            "name": "Teacher voice", "reference_asset_id": audio_id, "transcript": "测试", "consent_confirmed": True,
        })
        assert voice.status_code == 201, voice.text
        avatar = client.post("/api/saas/avatars", headers=source_headers, json={
            "name": "Teacher", "image_asset_id": image_id, "master_video_asset_id": video_id,
            "voice_profile_id": voice.json()["id"], "consent_confirmed": True,
        })
        assert avatar.status_code == 201, avatar.text

        with SessionLocal() as db:
            avatar_template = publish_template(db, kind="avatar", source_id=avatar.json()["id"])
            background_template = publish_template(db, kind="background", source_id=background_id)
            assert publish_template(db, kind="avatar", source_id=avatar.json()["id"]).id == avatar_template.id

        catalog = client.get("/api/saas/system-assets", headers=target_headers)
        assert catalog.status_code == 200
        assert {item["id"] for item in catalog.json()} >= {avatar_template.id, background_template.id}
        assert client.get(f"/api/saas/assets/{image_id}", headers=target_headers).status_code == 404
        assert client.get(f"/api/saas/system-assets/{background_template.id}/preview", headers=target_headers).status_code == 200

        imported_bg = client.post(f"/api/saas/system-assets/{background_template.id}/import", headers=target_headers)
        imported_avatar = client.post(f"/api/saas/system-assets/{avatar_template.id}/import", headers=target_headers)
        assert imported_bg.status_code == 200, imported_bg.text
        assert imported_avatar.status_code == 200, imported_avatar.text
        assert imported_bg.json()["imported"] is True
        assert imported_avatar.json()["imported"] is True
        again = client.post(f"/api/saas/system-assets/{avatar_template.id}/import", headers=target_headers)
        assert again.status_code == 200 and again.json()["imported"] is False
        assert again.json()["id"] == imported_avatar.json()["id"]
        with SessionLocal() as db:
            copied_bg = db.get(Asset, imported_bg.json()["id"])
            copied_avatar = db.get(Avatar, imported_avatar.json()["id"])
            assert copied_bg.tenant_id == target_tenant
            assert copied_bg.object_key != db.get(Asset, background_id).object_key
            assert copied_avatar.tenant_id == target_tenant
            assert copied_avatar.master_video_asset_id != video_id
            assert db.get(Asset, copied_avatar.master_video_asset_id).tenant_id == target_tenant
        assert client.get(f"/api/saas/assets/{imported_bg.json()['id']}/download", headers=target_headers).status_code == 200
        # Platform defaults do not consume the tenant's personal-avatar allowance.
        personal = client.post("/api/saas/avatars", headers=target_headers, json={
            "name": "Personal", "master_video_asset_id": copied_avatar.master_video_asset_id,
            "consent_confirmed": True,
        })
        assert personal.status_code == 201, personal.text
        over_limit = client.post("/api/saas/avatars", headers=target_headers, json={
            "name": "Too many personal avatars", "master_video_asset_id": copied_avatar.master_video_asset_id,
            "consent_confirmed": True,
        })
        assert over_limit.status_code == 402
