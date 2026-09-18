from __future__ import annotations

import shutil
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.saas.worker import MockCourseHandler, process_one
from app.saas_main import app


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required for mock worker acceptance test")


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


def test_mock_worker_creates_downloadable_output_and_reconciles_usage() -> None:
    with TestClient(app) as client:
        email = f"worker-{uuid4().hex[:8]}@example.com"
        registered = client.post(
            "/api/saas/auth/register",
            json={
                "email": email,
                "password": "correct-horse-battery-staple",
                "display_name": "Worker test",
                "workspace_name": "Worker test workspace",
            },
        )
        assert registered.status_code == 201, registered.text
        token = registered.json()["access_token"]

        ppt = _upload(client, token, "course.pptx", "ppt", b"fake-ppt")
        video = _upload(client, token, "master.mp4", "video", b"fake-video")
        audio = _upload(client, token, "voice.wav", "audio", b"fake-audio")

        voice = client.post(
            "/api/saas/voices",
            headers=_headers(token),
            json={
                "name": "Worker voice",
                "provider": "cosyvoice",
                "reference_asset_id": audio["id"],
                "transcript": "测试",
                "consent_confirmed": True,
            },
        ).json()
        avatar_response = client.post(
            "/api/saas/avatars",
            headers=_headers(token),
            json={
                "name": "Worker avatar",
                "master_video_asset_id": video["id"],
                "voice_profile_id": voice["id"],
                "consent_confirmed": True,
            },
        )
        assert avatar_response.status_code == 201, avatar_response.text
        avatar = avatar_response.json()
        course_response = client.post(
            "/api/saas/courses",
            headers=_headers(token),
            json={
                "title": "Worker acceptance",
                "ppt_asset_id": ppt["id"],
                "avatar_id": avatar["id"],
                "voice_profile_id": voice["id"],
                "script": [{"index": 1, "narration": "这是一个生成任务验收测试"}],
            },
        )
        assert course_response.status_code == 201, course_response.text
        course = course_response.json()

        render = client.post(
            f"/api/saas/courses/{course['id']}/render",
            headers=_headers(token),
            json={"engine": "mock", "estimated_seconds": 10, "audio_asset_id": audio["id"]},
        )
        assert render.status_code == 202, render.text
        job_id = render.json()["id"]

        # The CI suite intentionally shares one Redis service. Earlier tests may
        # leave other valid mock jobs in the same FIFO, so process until this
        # acceptance job reaches a terminal state instead of assuming it is the
        # very next queue item.
        job = None
        for _ in range(20):
            process_one(MockCourseHandler())
            job_response = client.get(f"/api/saas/jobs/{job_id}", headers=_headers(token))
            assert job_response.status_code == 200, job_response.text
            job = job_response.json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break

        assert job is not None
        assert job["status"] == "succeeded"
        assert job["output_asset_id"]
        assert job["video_seconds"] and job["video_seconds"] > 0

        course_after = client.get(f"/api/saas/courses/{course['id']}", headers=_headers(token)).json()
        assert course_after["status"] == "completed"
        assert course_after["output_asset_id"] == job["output_asset_id"]

        download = client.get(job["output_download_url"], headers=_headers(token))
        assert download.status_code == 200
        assert download.content

        subscription = client.get("/api/saas/billing/subscription", headers=_headers(token)).json()
        # Mock output is ~2 seconds; billing must settle against actual output, not the 10-second reservation.
        assert 0 < subscription["consumed_seconds"] <= 4
