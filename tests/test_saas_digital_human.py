from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas_main import app


def _register(client: TestClient) -> str:
    email = f"digital-human-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Digital Human Test",
            "workspace_name": "Digital Human Workspace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_integrated_digital_human_creation_and_readiness() -> None:
    with TestClient(app) as client:
        token = _register(client)
        response = client.post(
            "/api/saas/digital-humans",
            headers=_headers(token),
            data={
                "name": "Dan Instructor",
                "prompt": "professional lecturer",
                "voice_name": "Dan Voice",
                "voice_transcript": "大家好，欢迎来到今天的课程。",
                "portrait_consent": "true",
                "voice_consent": "true",
            },
            files={
                "image_file": ("portrait.jpg", BytesIO(b"fake-image"), "image/jpeg"),
                "master_video_file": ("master.mp4", BytesIO(b"fake-video"), "video/mp4"),
                "voice_file": ("voice.wav", BytesIO(b"fake-wave"), "audio/wav"),
            },
        )
        assert response.status_code == 201, response.text
        item = response.json()
        assert item["name"] == "Dan Instructor"
        assert item["image"]["kind"] == "image"
        assert item["master_video"]["kind"] == "video"
        assert item["voice"]["reference_asset"]["kind"] == "audio"
        assert item["voice"]["transcript"] == "大家好，欢迎来到今天的课程。"
        assert item["readiness"]["musetalk_ready"] is True

        updated_transcript = "大家好，欢迎来到今天的课程，很高兴和大家一起学习。"
        voice_update = client.patch(
            f"/api/saas/voices/{item['voice']['id']}",
            headers=_headers(token),
            json={"transcript": updated_transcript, "transcript_verified": True},
        )
        assert voice_update.status_code == 200, voice_update.text
        assert voice_update.json()["transcript"] == updated_transcript
        assert voice_update.json()["settings"]["transcript_verified"] is True

        refreshed = client.get(f"/api/saas/digital-humans/{item['id']}", headers=_headers(token))
        assert refreshed.status_code == 200
        assert refreshed.json()["voice"]["transcript"] == updated_transcript

        listing = client.get("/api/saas/digital-humans", headers=_headers(token))
        assert listing.status_code == 200
        assert any(row["id"] == item["id"] for row in listing.json())


def test_digital_human_requires_master_video_and_complete_voice() -> None:
    with TestClient(app) as client:
        token = _register(client)
        missing_video = client.post(
            "/api/saas/digital-humans",
            headers=_headers(token),
            data={
                "name": "Incomplete",
                "voice_name": "Voice",
                "voice_transcript": "测试",
                "portrait_consent": "true",
                "voice_consent": "true",
            },
            files={
                "image_file": ("portrait.jpg", BytesIO(b"fake-image"), "image/jpeg"),
                "voice_file": ("voice.wav", BytesIO(b"fake-wave"), "audio/wav"),
            },
        )
        assert missing_video.status_code == 422
        assert "master video" in missing_video.text.lower()

        missing_transcript = client.post(
            "/api/saas/digital-humans",
            headers=_headers(token),
            data={
                "name": "No transcript",
                "portrait_consent": "true",
                "voice_consent": "true",
            },
            files={
                "master_video_file": ("master.mp4", BytesIO(b"fake-video"), "video/mp4"),
                "voice_file": ("voice.wav", BytesIO(b"fake-wave"), "audio/wav"),
            },
        )
        assert missing_transcript.status_code == 422
        assert "transcript" in missing_transcript.text.lower()


def test_digital_human_asset_types_are_enforced() -> None:
    with TestClient(app) as client:
        token = _register(client)
        wrong_video_type = client.post(
            "/api/saas/digital-humans",
            headers=_headers(token),
            data={
                "name": "Wrong Type",
                "voice_transcript": "测试",
                "portrait_consent": "true",
                "voice_consent": "true",
            },
            files={
                "master_video_file": ("master.txt", BytesIO(b"not-video"), "text/plain"),
                "voice_file": ("voice.wav", BytesIO(b"fake-wave"), "audio/wav"),
            },
        )
        assert wrong_video_type.status_code == 415


def test_saas_shell_loads_integrated_avatar_ui() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert page.headers["permissions-policy"] == "camera=(), microphone=(self), geolocation=()"
        assert "/avatar-ui.js" in page.text
        script = client.get("/avatar-ui.js")
        assert script.status_code == 200
        assert "MediaRecorder" in script.text
        assert "/digital-humans" in script.text
        assert "现场录制克隆声音" in script.text
        assert 'id="dhUploadTranscript"' in script.text
        assert 'placeholder="请逐字填写录音中实际说出的完整文字' in script.text
        assert 'id="dhUploadTranscript">大家好' not in script.text
        assert "必须边播放边核对" in script.text
        assert "参考录音逐字稿" in script.text
        assert "核对 / 修正逐字稿" in script.text
        assert "步骤 2 · 播放录音并填写实际逐字稿" in script.text
        assert "method:'PATCH'" in script.text
