from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas.database import SessionLocal
from app.saas.render_snapshot_models import RenderTaskSnapshot
from app.saas_main import app


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": f"snapshot-{uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "snapshot",
            "workspace_name": "snapshot workspace",
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


def test_render_submission_freezes_script_voice_rules_and_asset_hashes() -> None:
    with TestClient(app) as client:
        token = _register(client)
        ppt = _upload(client, token, "snapshot.pptx", "ppt", b"snapshot-ppt")
        master = _upload(client, token, "snapshot.mp4", "video", b"snapshot-video")
        audio = _upload(client, token, "snapshot.wav", "audio", b"snapshot-audio")

        voice_response = client.post(
            "/api/saas/voices",
            headers=_headers(token),
            json={
                "name": "Snapshot Voice",
                "provider": "cosyvoice",
                "reference_asset_id": audio["id"],
                "transcript": "参考音频逐字稿",
                "settings": {"pause_seconds": 0.22},
                "consent_confirmed": True,
            },
        )
        assert voice_response.status_code == 201, voice_response.text
        voice = voice_response.json()

        avatar_response = client.post(
            "/api/saas/avatars",
            headers=_headers(token),
            json={
                "name": "Snapshot Avatar",
                "master_video_asset_id": master["id"],
                "voice_profile_id": voice["id"],
                "consent_confirmed": True,
            },
        )
        assert avatar_response.status_code == 201, avatar_response.text
        avatar = avatar_response.json()

        original_script = [
            {
                "index": 1,
                "narration": "Welcome to Youyou Story Time. Youyou is here.",
                "layout": "pip",
            }
        ]
        original_settings = {
            "speed": 1.0,
            "tts": {"pronunciation_replacements": {"Youyou": "Yoyo"}},
        }
        course_response = client.post(
            "/api/saas/courses",
            headers=_headers(token),
            json={
                "title": "Snapshot Course",
                "ppt_asset_id": ppt["id"],
                "avatar_id": avatar["id"],
                "voice_profile_id": voice["id"],
                "script": original_script,
                "settings": original_settings,
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
        job_id = render_response.json()["id"]

        with SessionLocal() as db:
            row = db.get(RenderTaskSnapshot, job_id)
            assert row is not None
            frozen = json.loads(row.snapshot_json)
            assert frozen["course"]["script"] == original_script
            assert frozen["course"]["settings"] == original_settings
            assert frozen["voice"]["transcript"] == "参考音频逐字稿"
            assert frozen["voice"]["settings"] == {"pause_seconds": 0.22}
            assert frozen["assets"][ppt["id"]]["sha256"] == ppt["sha256"]
            assert frozen["assets"][master["id"]]["sha256"] == master["sha256"]
            first_hash = row.snapshot_hash

        changed = client.patch(
            f"/api/saas/courses/{course['id']}",
            headers=_headers(token),
            json={
                "script": [{"index": 1, "narration": "CHANGED AFTER SUBMIT", "layout": "full_slide"}],
                "settings": {"speed": 1.25, "tts": {"pronunciation_replacements": {"Youyou": "changed"}}},
            },
        )
        assert changed.status_code == 200, changed.text

        with SessionLocal() as db:
            row = db.get(RenderTaskSnapshot, job_id)
            frozen = json.loads(row.snapshot_json)
            assert row.snapshot_hash == first_hash
            assert frozen["course"]["script"] == original_script
            assert frozen["course"]["settings"] == original_settings
