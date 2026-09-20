from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.saas import distributed_worker_api
from app.saas.database import SessionLocal
from app.saas.distributed_render_models import RenderArtifact, WorkerEnrollment, WorkerHeartbeatSample, WorkerNode
from app.saas.distributed_scheduler import hash_secret, initialize_parent_graph, publish_prepared_pages
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


def test_worker_descriptor_prefers_signed_download_and_keeps_proxy_fallback(monkeypatch) -> None:
    original = saas_settings.distributed_direct_downloads
    object.__setattr__(saas_settings, "distributed_direct_downloads", True)
    monkeypatch.setattr(
        distributed_worker_api.object_store,
        "signed_get_url",
        lambda key: f"https://objects.example.test/{key}?signature=abc",
    )
    try:
        descriptor = distributed_worker_api._file_descriptor(
            SimpleNamespace(
                id="asset-1",
                name="master.mp4",
                content_type="video/mp4",
                size_bytes=123,
                sha256="abc123",
                object_key="tenant/assets/master.mp4",
            ),
            task_id="task-1",
        )
        assert descriptor["transfer_mode"] == "direct"
        assert descriptor["url"].startswith("https://objects.example.test/tenant/assets/master.mp4")
        assert descriptor["fallback_url"] == "/api/saas/internal/render/tasks/task-1/assets/asset-1"
        assert descriptor["url_expires_in"] == saas_settings.storage_signed_url_seconds
    finally:
        object.__setattr__(saas_settings, "distributed_direct_downloads", original)


def test_worker_descriptor_uses_proxy_when_direct_downloads_disabled(monkeypatch) -> None:
    original = saas_settings.distributed_direct_downloads
    object.__setattr__(saas_settings, "distributed_direct_downloads", False)
    monkeypatch.setattr(
        distributed_worker_api.object_store,
        "signed_get_url",
        lambda _key: (_ for _ in ()).throw(AssertionError("signing should not run")),
    )
    try:
        descriptor = distributed_worker_api._file_descriptor(
            SimpleNamespace(
                id="asset-2",
                name="reference.wav",
                content_type="audio/wav",
                size_bytes=456,
                sha256="def456",
                object_key="tenant/assets/reference.wav",
            ),
            task_id="task-2",
        )
        assert descriptor["transfer_mode"] == "proxy"
        assert descriptor["url"] == "/api/saas/internal/render/tasks/task-2/assets/asset-2"
        assert descriptor["fallback_url"] is None
    finally:
        object.__setattr__(saas_settings, "distributed_direct_downloads", original)


def test_direct_artifact_upload_session_commit_and_idempotency(monkeypatch) -> None:
    original_enabled = saas_settings.distributed_render_enabled
    original_direct = saas_settings.distributed_direct_uploads
    object.__setattr__(saas_settings, "distributed_render_enabled", True)
    object.__setattr__(saas_settings, "distributed_direct_uploads", True)
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
                            "narration": "direct upload",
                            "estimated_seconds": 5,
                            "master_video_asset_id": master["id"],
                        }
                    ],
                )
                db.commit()

            _promote_superuser(user_token)
            provision = client.post(
                "/api/saas/distributed/workers",
                headers=_headers(user_token),
                json={"name": "direct-upload-mini", "slots_total": 1},
            )
            assert provision.status_code == 201, provision.text
            worker_headers = {"Authorization": f"Bearer {provision.json()['token']}"}
            register = client.post(
                "/api/saas/internal/render/register",
                headers=worker_headers,
                json={
                    "name": "direct-upload-mini",
                    "host": "direct-upload-mini.local",
                    "platform": "macOS",
                    "machine": "arm64",
                    "slots_total": 1,
                    "capabilities": ["musetalk"],
                    "versions": {"test": "1"},
                    "code_version": "0.5.0",
                    "model_version": "musetalk-mlx",
                    "render_contract_version": saas_settings.render_contract_version,
                },
            )
            assert register.status_code == 200, register.text

            claim = client.post("/api/saas/internal/render/tasks/claim", headers=worker_headers)
            assert claim.status_code == 200, claim.text
            task = claim.json()["task"]
            assert task is not None
            lease_headers = {
                **worker_headers,
                "X-Attempt-Id": task["attempt_id"],
                "X-Lease-Token": task["lease_token"],
            }

            payload = b"direct-page-video"
            digest = hashlib.sha256(payload).hexdigest()
            signed_keys: list[str] = []
            monkeypatch.setattr(
                distributed_worker_api.object_store,
                "signed_put_url",
                lambda key: signed_keys.append(key) or f"https://objects.example.test/{key}?signature=put",
            )
            monkeypatch.setattr(
                distributed_worker_api.object_store,
                "object_size",
                lambda key: len(payload) if key in signed_keys else None,
            )

            session = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video/direct-upload",
                headers=lease_headers,
                json={"size_bytes": len(payload), "sha256": digest},
            )
            assert session.status_code == 200, session.text
            session_body = session.json()
            assert session_body["mode"] == "direct"
            assert session_body["object_key"].endswith(
                f"/attempts/{task['attempt_id']}/page_video.mp4"
            )
            assert session_body["upload_url"].startswith("https://objects.example.test/")

            wrong_key = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video/direct-commit",
                headers=lease_headers,
                json={
                    "object_key": "another-tenant/forbidden.mp4",
                    "size_bytes": len(payload),
                    "sha256": digest,
                },
            )
            assert wrong_key.status_code == 409

            committed = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video/direct-commit",
                headers=lease_headers,
                json={
                    "object_key": session_body["object_key"],
                    "size_bytes": len(payload),
                    "sha256": digest,
                },
            )
            assert committed.status_code == 200, committed.text
            assert committed.json()["completed"] is True

            repeated = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_video/direct-commit",
                headers=lease_headers,
                json={
                    "object_key": session_body["object_key"],
                    "size_bytes": len(payload),
                    "sha256": digest,
                },
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["idempotent"] is True

            audio_session = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_audio/direct-upload",
                headers=lease_headers,
                json={"size_bytes": len(payload), "sha256": digest},
            )
            assert audio_session.status_code == 200, audio_session.text
            audio_body = audio_session.json()
            audio_commit = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_audio/direct-commit",
                headers=lease_headers,
                json={
                    "object_key": audio_body["object_key"],
                    "size_bytes": len(payload),
                    "sha256": digest,
                },
            )
            assert audio_commit.status_code == 200, audio_commit.text

            completed = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/complete",
                headers=worker_headers,
                json={
                    "attempt_id": task["attempt_id"],
                    "lease_token": task["lease_token"],
                    "metrics": {"render_seconds": 1.0},
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
                },
            )
            assert completed.status_code == 200, completed.text

            with SessionLocal() as db:
                artifact = db.scalar(
                    select(RenderArtifact).where(
                        RenderArtifact.attempt_id == task["attempt_id"],
                        RenderArtifact.kind == "page_video",
                    )
                )
                assert artifact is not None
                assert artifact.object_key == session_body["object_key"]
                assert artifact.size_bytes == len(payload)
                assert artifact.sha256 == digest
                metadata = json.loads(artifact.metadata_json)
                assert metadata["transfer_mode"] == "direct"
                assert metadata["media"]["frame_count"] == 25
    finally:
        object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)
        object.__setattr__(saas_settings, "distributed_direct_uploads", original_direct)


def test_direct_artifact_upload_falls_back_when_backend_cannot_sign(monkeypatch) -> None:
    original_enabled = saas_settings.distributed_render_enabled
    original_direct = saas_settings.distributed_direct_uploads
    object.__setattr__(saas_settings, "distributed_render_enabled", True)
    object.__setattr__(saas_settings, "distributed_direct_uploads", True)
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
                            "narration": "proxy fallback",
                            "estimated_seconds": 5,
                            "master_video_asset_id": master["id"],
                        }
                    ],
                )
                db.commit()

            _promote_superuser(user_token)
            provision = client.post(
                "/api/saas/distributed/workers",
                headers=_headers(user_token),
                json={"name": "proxy-fallback-mini", "slots_total": 1},
            )
            worker_headers = {"Authorization": f"Bearer {provision.json()['token']}"}
            register = client.post(
                "/api/saas/internal/render/register",
                headers=worker_headers,
                json={
                    "name": "proxy-fallback-mini",
                    "host": "proxy-fallback-mini.local",
                    "platform": "macOS",
                    "machine": "arm64",
                    "slots_total": 1,
                    "capabilities": ["musetalk"],
                    "versions": {},
                    "code_version": "0.5.0",
                    "model_version": "musetalk-mlx",
                    "render_contract_version": saas_settings.render_contract_version,
                },
            )
            assert register.status_code == 200, register.text
            claim = client.post("/api/saas/internal/render/tasks/claim", headers=worker_headers)
            task = claim.json()["task"]
            assert task is not None
            lease_headers = {
                **worker_headers,
                "X-Attempt-Id": task["attempt_id"],
                "X-Lease-Token": task["lease_token"],
            }
            monkeypatch.setattr(distributed_worker_api.object_store, "signed_put_url", lambda _key: None)
            payload = b"fallback"
            session = client.post(
                f"/api/saas/internal/render/tasks/{task['id']}/artifacts/page_audio/direct-upload",
                headers=lease_headers,
                json={
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
            assert session.status_code == 200, session.text
            assert session.json() == {"mode": "proxy", "completed": False}
    finally:
        object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)
        object.__setattr__(saas_settings, "distributed_direct_uploads", original_direct)


def test_worker_enrollment_is_single_use_and_issues_real_credential() -> None:
    with TestClient(app) as client:
        token = _register_user(client)
        _promote_superuser(token)

        created = client.post(
            "/api/saas/distributed/workers/enrollments",
            headers=_headers(token),
            json={"name": "remote-enroll-mini", "slots_total": 1},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        code = payload["enrollment_code"]
        node_id = payload["worker"]["id"]
        assert code.startswith("enr_")
        assert payload["worker"]["status"] == "pending"
        assert payload["worker"]["accepting_tasks"] is False

        with SessionLocal() as db:
            enrollment = db.scalar(
                select(WorkerEnrollment).where(WorkerEnrollment.node_id == node_id)
            )
            node = db.get(WorkerNode, node_id)
            assert enrollment is not None
            assert node is not None
            assert enrollment.token_hash == hash_secret(code)
            assert enrollment.token_hash != code
            assert enrollment.used_at is None
            pending_hash = node.credential_hash

        enrolled = client.post(
            "/api/saas/internal/render/enroll",
            json={
                "enrollment_code": code,
                "name": "remote-enroll-mini",
                "host": "remote-enroll-mini.local",
                "platform": "macOS",
                "machine": "arm64",
            },
        )
        assert enrolled.status_code == 200, enrolled.text
        worker_token = enrolled.json()["token"]
        assert worker_token.startswith(f"wrk_{node_id}_")
        assert enrolled.json()["worker"]["status"] == "offline"
        assert enrolled.json()["worker"]["accepting_tasks"] is True

        replay = client.post(
            "/api/saas/internal/render/enroll",
            json={"enrollment_code": code},
        )
        assert replay.status_code == 401

        worker_headers = {"Authorization": f"Bearer {worker_token}"}
        original_enabled = saas_settings.distributed_render_enabled
        object.__setattr__(saas_settings, "distributed_render_enabled", True)
        try:
            pre_register_claim = client.post(
                "/api/saas/internal/render/tasks/claim",
                headers=worker_headers,
            )
            assert pre_register_claim.status_code == 409
        finally:
            object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)

        register = client.post(
            "/api/saas/internal/render/register",
            headers=worker_headers,
            json={
                "name": "remote-enroll-mini",
                "host": "remote-enroll-mini.local",
                "platform": "macOS",
                "machine": "arm64",
                "slots_total": 1,
                "capabilities": ["musetalk"],
                "versions": {"agent": "v3"},
                "code_version": "0.5.0",
                "model_version": "musetalk-mlx",
                "render_contract_version": saas_settings.render_contract_version,
            },
        )
        assert register.status_code == 200, register.text

        with SessionLocal() as db:
            enrollment = db.scalar(
                select(WorkerEnrollment).where(WorkerEnrollment.node_id == node_id)
            )
            node = db.get(WorkerNode, node_id)
            assert enrollment is not None and enrollment.used_at is not None
            assert node is not None
            assert node.credential_hash == hash_secret(worker_token)
            assert node.credential_hash != pending_hash


def test_expired_worker_enrollment_is_rejected() -> None:
    with TestClient(app) as client:
        token = _register_user(client)
        _promote_superuser(token)
        created = client.post(
            "/api/saas/distributed/workers/enrollments",
            headers=_headers(token),
            json={"name": "expired-enroll-mini", "slots_total": 1},
        )
        assert created.status_code == 201, created.text
        code = created.json()["enrollment_code"]
        node_id = created.json()["worker"]["id"]

        with SessionLocal() as db:
            enrollment = db.scalar(
                select(WorkerEnrollment).where(WorkerEnrollment.node_id == node_id)
            )
            assert enrollment is not None
            enrollment.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()

        expired = client.post(
            "/api/saas/internal/render/enroll",
            json={"enrollment_code": code},
        )
        assert expired.status_code == 401
        with SessionLocal() as db:
            enrollment = db.scalar(
                select(WorkerEnrollment).where(WorkerEnrollment.node_id == node_id)
            )
            assert enrollment is not None
            assert enrollment.used_at is None


def test_allowed_task_assets_include_content_shot_media(monkeypatch) -> None:
    monkeypatch.setattr(
        distributed_worker_api,
        "_snapshot_payload",
        lambda _db, _parent: {
            "avatar": {"master_video_asset_id": "master"},
            "voice": {"reference_asset_id": "reference"},
            "pages": [
                {
                    "index": 1,
                    "media_cues": [
                        {"id": "cue-1", "asset_id": "shot-from-snapshot"},
                    ],
                }
            ],
        },
    )
    task = SimpleNamespace(
        parent_job_id="parent-1",
        slide_index=1,
        payload_json=json.dumps(
            {
                "media_cues": [{"id": "cue-2", "asset_id": "shot-from-payload"}],
                "override": {
                    "media_cues": [{"id": "cue-3", "asset_id": "shot-from-override"}],
                },
            }
        ),
    )
    allowed = distributed_worker_api._allowed_asset_ids(None, task)
    assert {"master", "reference", "shot-from-snapshot", "shot-from-payload", "shot-from-override"}.issubset(allowed)


def test_worker_management_metrics_group_and_editing() -> None:
    with TestClient(app) as client:
        token = _register_user(client)
        _promote_superuser(token)

        provision = client.post(
            "/api/saas/distributed/workers",
            headers=_headers(token),
            json={"name": "managed-mini", "group_name": "production", "slots_total": 2},
        )
        assert provision.status_code == 201, provision.text
        worker = provision.json()["worker"]
        worker_token = provision.json()["token"]
        assert worker["group_name"] == "production"
        worker_headers = {"Authorization": f"Bearer {worker_token}"}

        register = client.post(
            "/api/saas/internal/render/register",
            headers=worker_headers,
            json={
                "name": "managed-mini",
                "host": "managed-mini.local",
                "platform": "macOS",
                "machine": "arm64",
                "slots_total": 2,
                "capabilities": ["musetalk"],
                "versions": {"python": "3.11"},
                "code_version": "0.5.0",
                "model_version": "musetalk-mlx",
                "render_contract_version": saas_settings.render_contract_version,
            },
        )
        assert register.status_code == 200, register.text

        heartbeat = client.post(
            "/api/saas/internal/render/heartbeat",
            headers=worker_headers,
            json={
                "disk_free_bytes": 100 * 1024**3,
                "memory_available_mb": 8192,
                "cpu_percent": 42.5,
                "memory_percent": 51.25,
            },
        )
        assert heartbeat.status_code == 200, heartbeat.text
        payload = heartbeat.json()["worker"]
        assert payload["cpu_percent"] == 42.5
        assert payload["memory_percent"] == 51.25

        heartbeat_again = client.post(
            "/api/saas/internal/render/heartbeat",
            headers=worker_headers,
            json={
                "disk_free_bytes": 99 * 1024**3,
                "memory_available_mb": 8000,
                "cpu_percent": 44.0,
                "memory_percent": 52.0,
            },
        )
        assert heartbeat_again.status_code == 200, heartbeat_again.text

        with SessionLocal() as db:
            node = db.get(WorkerNode, worker["id"])
            assert node is not None
            assert node.group_name == "production"
            samples = db.scalars(
                select(WorkerHeartbeatSample).where(
                    WorkerHeartbeatSample.node_id == worker["id"]
                )
            ).all()
            assert len(samples) == 1
            sample = samples[0]
            assert sample.cpu_percent == 42.5
            assert sample.memory_percent == 51.25

        overview = client.get("/api/saas/admin/workers/overview", headers=_headers(token))
        assert overview.status_code == 200, overview.text
        assert overview.json()["groups"]["production"]["total"] >= 1

        edited = client.patch(
            f"/api/saas/admin/workers/{worker['id']}",
            headers=_headers(token),
            json={
                "name": "managed-mini-renamed",
                "group_name": "mac-cluster",
                "slots_total": 2,
                "notes": "primary production Mac",
            },
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["name"] == "managed-mini-renamed"
        assert edited.json()["group_name"] == "mac-cluster"
        assert edited.json()["notes"] == "primary production Mac"

        restarted = client.post(
            "/api/saas/internal/render/register",
            headers=worker_headers,
            json={
                "name": "runtime-name-should-not-win",
                "host": "managed-mini.local",
                "platform": "macOS",
                "machine": "arm64",
                "slots_total": 1,
                "capabilities": ["musetalk"],
                "versions": {"python": "3.11"},
                "code_version": "0.5.0",
                "model_version": "musetalk-mlx",
                "render_contract_version": saas_settings.render_contract_version,
            },
        )
        assert restarted.status_code == 200, restarted.text
        assert restarted.json()["worker"]["name"] == "managed-mini-renamed"
        assert restarted.json()["worker"]["slots_total"] == 2

        detail = client.get(
            f"/api/saas/admin/workers/{worker['id']}",
            headers=_headers(token),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["worker"]["group_name"] == "mac-cluster"
        assert detail.json()["health_series"]

        with SessionLocal() as db:
            node = db.get(WorkerNode, worker["id"])
            assert node is not None
            node.slots_busy = 2
            db.commit()

        too_low = client.patch(
            f"/api/saas/admin/workers/{worker['id']}",
            headers=_headers(token),
            json={"slots_total": 1},
        )
        assert too_low.status_code == 409
>>>>>>> saas/feat/worker-control-center
