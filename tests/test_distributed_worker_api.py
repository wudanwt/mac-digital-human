from __future__ import annotations

import hashlib
from pathlib import Path
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas.database import SessionLocal
from app.saas.distributed_scheduler import initialize_parent_graph, publish_prepared_pages
from app.saas.distributed_worker_api import _sha256_path
from app.saas.models import User
from app.saas.security import decode_access_token
from app.saas.settings import saas_settings
from app.saas_main import app


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_user(client: TestClient) -> str:
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": f"worker-api-{uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "worker api",
            "workspace_name": "worker api workspace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _promote_superuser(token: str) -> None:
    principal = decode_access_token(token)
    with SessionLocal() as db:
        user = db.get(User, principal.user_id)
        assert user is not None
        user.is_superuser = True
        db.commit()


def _upload(client: TestClient, token: str, name: str, kind: str, content: bytes) -> dict:
    response = client.post(
        "/api/saas/assets",
        headers=_headers(token),
        data={"kind": kind},
        files={"file": (name, BytesIO(content), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _parent(client: TestClient, token: str) -> tuple[str, dict, dict, dict]:
    ppt = _upload(client, token, "worker.pptx", "ppt", b"ppt-bytes")
    master = _upload(client, token, "worker.mp4", "video", b"master-video-bytes")
    audio = _upload(client, token, "worker.wav", "audio", b"reference-audio-bytes")
    voice_response = client.post(
        "/api/saas/voices",
        headers=_headers(token),
        json={
            "name": "Worker Voice",
            "provider": "cosyvoice",
            "reference_asset_id": audio["id"],
            "transcript": "reference",
            "consent_confirmed": True,
        },
    )
    assert voice_response.status_code == 201, voice_response.text
    voice = voice_response.json()
    avatar_response = client.post(
        "/api/saas/avatars",
        headers=_headers(token),
        json={
            "name": "Worker Avatar",
            "master_video_asset_id": master["id"],
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
            "title": "Worker API course",
            "ppt_asset_id": ppt["id"],
            "avatar_id": avatar["id"],
            "voice_profile_id": voice["id"],
            "script": [{"index": 1, "narration": "hello worker"}],
        },
    )
    assert course_response.status_code == 201, course_response.text
    render = client.post(
        f"/api/saas/courses/{course_response.json()['id']}/render",
        headers=_headers(token),
        json={"engine": "mock", "estimated_seconds": 1, "audio_asset_id": audio["id"]},
    )
    assert render.status_code == 202, render.text
    return render.json()["id"], ppt, master, audio


def test_worker_api_auth_range_resume_and_idempotent_complete() -> None:
    original_enabled = saas_settings.distributed_render_enabled
    object.__setattr__(saas_settings, "distributed_render_enabled", True)
    try:
        with TestClient(app) as client:
            user_token = _register_user(client)
            parent_job_id, _ppt, master, _audio = _parent(client, user_token)

            with SessionLocal() as db:
                initialize_parent_graph(db, parent_job_id)
                publish_prepared_pages(
                    db,
                    parent_job_id=parent_job_id,
                    pages=[
                        {
                            "index": 1,
                            "narration": "hello worker",
                            "estimated_seconds": 5,
                            "master_video_asset_id": master["id"],
                        }
                    ],
                )
                db.commit()

            # Worker credentials are platform infrastructure and cannot be minted
            # by an ordinary tenant owner.
            forbidden = client.post(
                "/api/saas/distributed/workers",
                headers=_headers(user_token),
                json={"name": "forbidden-mini", "slots_total": 1},
            )
            assert forbidden.status_code == 403
            _promote_superuser(user_token)

            provision = client.post(
                "/api/saas/distributed/workers",
                headers=_headers(user_token),
                json={"name": "mini-api-test", "slots_total": 1},
            )
            assert provision.status_code == 201, provision.text
            worker_token = provision.json()["token"]
            worker_headers = {"Authorization": f"Bearer {worker_token}"}

            register = client.post(
                "/api/saas/internal/render/register",
                headers=worker_headers,
                json={
                    "name": "mini-api-test",
                    "host": "mini.local",
                    "platform": "macOS",
                    "machine": "arm64",
                    "slots_total": 1,
                    "capabilities": ["musetalk", "transparent-avatar-compose"],
                    "versions": {"test": "1"},
                    "code_version": "0.5.0",
                    "model_version": "musetalk-mlx",
                    "render_contract_version": saas_settings.render_contract_version,
                },
            )
            assert register.status_code == 200, register.text

            heartbeat = client.post(
                "/api/saas/internal/render/heartbeat",
                headers=worker_headers,
                json={"disk_free_bytes": 100 * 1024**3, "memory_available_mb": 12000},
            )
            assert heartbeat.status_code == 200, heartbeat.text

            claim = client.post("/api/saas/internal/render/tasks/claim", headers=worker_headers)
            assert claim.status_code == 200, claim.text
            task = claim.json()["task"]
            assert task is not None
            assert task["slide_index"] == 1
            lease_headers = {
                **worker_headers,
                "X-Attempt-Id": task["attempt_id"],
                "X-Lease-Token": task["lease_token"],
            }

            master_descriptor = next(item for item in task["assets"] if item["id"] == master["id"])
            ranged = client.get(master_descriptor["url"], headers={**lease_headers, "Range": "bytes=0-5"})
            assert ranged.status_code == 206, ranged.text
            assert ranged.content == b"master"
            assert ranged.headers["accept-ranges"] == "bytes"

            video = b"0123456789abcdef"
            video_hash = hashlib.sha256(video).hexdigest()
            first = client.put(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video",
                headers={**lease_headers, "Content-Range": f"bytes 0-7/{len(video)}"},
                content=video[:8],
            )
            assert first.status_code == 200, first.text
            assert first.json()["completed"] is False
            status = client.get(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video/upload",
                headers=lease_headers,
            )
            assert status.status_code == 200
            assert status.json()["received_bytes"] == 8
            second = client.put(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video",
                headers={
                    **lease_headers,
                    "Content-Range": f"bytes 8-15/{len(video)}",
                    "X-Content-SHA256": video_hash,
                },
                content=video[8:],
            )
            assert second.status_code == 200, second.text
            assert second.json()["completed"] is True

            audio = b"fake-wav-audio"
            audio_hash = hashlib.sha256(audio).hexdigest()
            audio_upload = client.put(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_audio",
                headers={
                    **lease_headers,
                    "Content-Range": f"bytes 0-{len(audio) - 1}/{len(audio)}",
                    "X-Content-SHA256": audio_hash,
                },
                content=audio,
            )
            assert audio_upload.status_code == 200, audio_upload.text

            complete_payload = {
                "attempt_id": task["attempt_id"],
                "lease_token": task["lease_token"],
                "metrics": {"render_seconds": 1.2},
                "media": {
                    "video_seconds": 1.0,
                    "audio_seconds": 1.0,
                    "frame_count": 25,
                    "encoding": {
                        "width": 1280,
                        "height": 720,
                        "fps": "25/1",
                        "pix_fmt": "yuv420p",
                        "video_codec": "h264",
                        "audio_codec": "aac",
                        "audio_sample_rate": 24000,
                        "audio_channels": 1,
                    },
                },
            }
            completed = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/complete",
                headers=worker_headers,
                json=complete_payload,
            )
            assert completed.status_code == 200, completed.text
            assert completed.json()["ok"] is True
            repeated = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/complete",
                headers=worker_headers,
                json=complete_payload,
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["idempotent"] is True
    finally:
        object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)


def test_worker_artifact_hash_streams_file(monkeypatch, tmp_path: Path) -> None:
    payload = b"x" * (3 * 1024 * 1024 + 17)
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: (_ for _ in ()).throw(AssertionError("read_bytes must not be used for artifact hashing")),
    )
    assert _sha256_path(path) == hashlib.sha256(payload).hexdigest()


def test_incompatible_worker_recovers_after_compatible_registration() -> None:
    with TestClient(app) as client:
        token = _register_user(client)
        _promote_superuser(token)
        provision = client.post(
            "/api/saas/distributed/workers",
            headers=_headers(token),
            json={"name": "recovering-mini", "slots_total": 1},
        )
        assert provision.status_code == 201, provision.text
        worker_token = provision.json()["token"]
        worker_headers = {"Authorization": f"Bearer {worker_token}"}
        base_payload = {
            "name": "recovering-mini",
            "host": "recovering-mini.local",
            "platform": "macOS",
            "machine": "arm64",
            "slots_total": 1,
            "capabilities": ["musetalk"],
            "versions": {"test": "1"},
            "code_version": "0.5.0",
            "model_version": "musetalk-mlx",
        }

        rejected = client.post(
            "/api/saas/internal/render/register",
            headers=worker_headers,
            json={**base_payload, "render_contract_version": "outdated-contract"},
        )
        assert rejected.status_code == 409, rejected.text

        workers = client.get("/api/saas/distributed/workers", headers=_headers(token))
        assert workers.status_code == 200, workers.text
        rejected_node = next(item for item in workers.json() if item["name"] == "recovering-mini")
        assert rejected_node["status"] == "incompatible"
        assert rejected_node["accepting_tasks"] is False

        recovered = client.post(
            "/api/saas/internal/render/register",
            headers=worker_headers,
            json={**base_payload, "render_contract_version": saas_settings.render_contract_version},
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["worker"]["accepting_tasks"] is True
        assert recovered.json()["worker"]["status"] == "online"
