from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.saas.auxiliary_task_models import AuxiliaryTaskLease
from app.saas import remote_page_worker
from app.saas.auxiliary_worker_api import reap_expired_auxiliary_leases
from app.saas.avatar_matting_models import AvatarMattingJob
from app.saas.database import SessionLocal
from app.saas.distributed_render_models import WorkerNode
from app.saas.distributed_scheduler import hash_secret
from app.saas.models import Asset, Avatar, Course, Tenant, User, VoiceProfile
from app.saas.settings import saas_settings
from app.saas.speech_preview_models import SpeechPreviewJob
from app.saas.speech_preview_service import synthesis_fingerprint
from app.saas.storage import object_store
from app.saas_main import app


def _upload(client: TestClient, worker_token: str, task: dict, kind: str, content: bytes):
    return client.put(
        f"/api/saas/internal/render/aux/{task['id']}/artifacts/{kind}",
        headers={
            "Authorization": f"Bearer {worker_token}",
            "X-Lease-Token": task["lease_token"],
            "X-Content-SHA256": hashlib.sha256(content).hexdigest(),
        },
        content=content,
    )


def test_remote_auxiliary_claim_transfer_complete_and_reap() -> None:
    original_enabled = saas_settings.distributed_render_enabled
    object.__setattr__(saas_settings, "distributed_render_enabled", True)
    try:
        with TestClient(app) as client:
            suffix = uuid4().hex
            worker_token = f"worker-{suffix}"
            with SessionLocal() as db:
                user = User(email=f"aux-{suffix}@example.com", password_hash="test")
                db.add(user)
                db.flush()
                tenant = Tenant(name="Auxiliary test", slug=f"aux-{suffix}", owner_user_id=user.id)
                db.add(tenant)
                db.flush()
                master_bytes = b"fake-master-video"
                reference_bytes = b"fake-reference-audio"
                master_key = f"{tenant.id}/test-master.mp4"
                reference_key = f"{tenant.id}/test-reference.wav"
                master = Asset(
                    tenant_id=tenant.id, user_id=user.id, kind="video", name="master.mp4",
                    object_key=master_key, uri=object_store.put_stream(BytesIO(master_bytes), master_key),
                    content_type="video/mp4", size_bytes=len(master_bytes), sha256=hashlib.sha256(master_bytes).hexdigest(),
                )
                reference = Asset(
                    tenant_id=tenant.id, user_id=user.id, kind="audio", name="reference.wav",
                    object_key=reference_key, uri=object_store.put_stream(BytesIO(reference_bytes), reference_key),
                    content_type="audio/wav", size_bytes=len(reference_bytes), sha256=hashlib.sha256(reference_bytes).hexdigest(),
                )
                db.add_all([master, reference])
                db.flush()
                voice = VoiceProfile(tenant_id=tenant.id, name="voice", reference_asset_id=reference.id, transcript="hello")
                avatar = Avatar(tenant_id=tenant.id, name="avatar", master_video_asset_id=master.id)
                course = Course(tenant_id=tenant.id, user_id=user.id, title="course", settings_json="{}")
                db.add_all([voice, avatar, course])
                db.flush()
                speech = SpeechPreviewJob(
                    tenant_id=tenant.id, user_id=user.id, course_id=course.id, voice_profile_id=voice.id,
                    slide_index=1, scope="page", text="Hello world", text_hash=synthesis_fingerprint(
                        text="Hello world", scope="page", voice=voice, course_settings={}
                    ),
                )
                matting = AvatarMattingJob(
                    tenant_id=tenant.id, user_id=user.id, avatar_id=avatar.id, source_asset_id=master.id,
                )
                node = WorkerNode(
                    name="remote-test", credential_hash=hash_secret(worker_token), status="online",
                    accepting_tasks=True, slots_total=1, slots_busy=0,
                    capabilities_json=json.dumps(["musetalk", "portrait-matting", "speech-preview"]),
                )
                db.add_all([speech, matting, node])
                db.commit()
                speech_id, matting_id = speech.id, matting.id
                # SQLite drops timezone info on round-trip; calculate the
                # production fingerprint from the persisted voice snapshot.
                db.refresh(voice)
                speech.text_hash = synthesis_fingerprint(
                    text=speech.text, scope=speech.scope, voice=voice, course_settings={}
                )
                db.commit()

            headers = {"Authorization": f"Bearer {worker_token}"}
            claim = client.post("/api/saas/internal/render/aux/claim", headers=headers)
            assert claim.status_code == 200, claim.text
            task = claim.json()["task"]
            assert task["kind"] == "speech_preview"
            assert client.post("/api/saas/internal/render/aux/claim", headers=headers).json()["task"] is None
            source = client.get(
                task["assets"][0]["url"],
                headers={**headers, "X-Lease-Token": task["lease_token"], "Range": "bytes=0-3"},
            )
            assert source.status_code == 206 and source.content == reference_bytes[:4]
            denied = client.get(task["assets"][0]["url"], headers={**headers, "X-Lease-Token": "wrong"})
            assert denied.status_code == 409
            bad = client.put(
                f"/api/saas/internal/render/aux/{task['id']}/artifacts/audio",
                headers={**headers, "X-Lease-Token": task["lease_token"], "X-Content-SHA256": "0" * 64},
                content=b"wav",
            )
            assert bad.status_code == 422
            assert _upload(client, worker_token, task, "audio", b"generated-wav").status_code == 200
            complete = client.post(
                f"/api/saas/internal/render/aux/{task['id']}/complete",
                headers=headers, json={"lease_token": task["lease_token"]},
            )
            assert complete.status_code == 200, complete.text
            assert complete.json()["status"] == "succeeded"
            assert client.post(
                f"/api/saas/internal/render/aux/{task['id']}/complete",
                headers=headers, json={"lease_token": task["lease_token"]},
            ).status_code == 409

            task = client.post("/api/saas/internal/render/aux/claim", headers=headers).json()["task"]
            assert task["kind"] == "avatar_matting"
            for kind in ("alpha", "poster", "white"):
                assert _upload(client, worker_token, task, kind, kind.encode()).status_code == 200
            complete = client.post(
                f"/api/saas/internal/render/aux/{task['id']}/complete",
                headers=headers, json={"lease_token": task["lease_token"], "metadata": {"frames": 12}},
            )
            assert complete.status_code == 200, complete.text
            with SessionLocal() as db:
                assert db.get(SpeechPreviewJob, speech_id).audio_asset_id is not None
                result = db.get(AvatarMattingJob, matting_id)
                assert result.alpha_asset_id and result.poster_asset_id and result.white_preview_asset_id
                assert json.loads(result.metadata_json)["frames"] == 12

                result.status = "queued"
                result.alpha_asset_id = result.poster_asset_id = result.white_preview_asset_id = None
                db.commit()
            task = client.post("/api/saas/internal/render/aux/claim", headers=headers).json()["task"]
            with SessionLocal() as db:
                lease = db.get(AuxiliaryTaskLease, task["id"])
                lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
                assert reap_expired_auxiliary_leases(db) == 1
                db.commit()
                assert db.get(AvatarMattingJob, matting_id).status == "queued"
            assert client.post(
                f"/api/saas/internal/render/aux/{task['id']}/renew",
                headers=headers, json={"lease_token": task["lease_token"]},
            ).status_code == 409
    finally:
        object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)


def test_remote_worker_executes_both_auxiliary_kinds(monkeypatch, tmp_path: Path) -> None:
    class FakeApi:
        def __init__(self):
            self.completed = []
            self.failed = []
            self.uploaded = []

        def renew_auxiliary(self, task):
            return "later"

        def download(self, task, descriptor, destination):
            destination.write_bytes(b"input")
            return destination

        def progress_auxiliary(self, task, progress, stage):
            pass

        def upload_auxiliary(self, task, kind, source):
            assert source.exists()
            self.uploaded.append(kind)

        def complete_auxiliary(self, task, metadata):
            self.completed.append((task["kind"], metadata))

        def fail_auxiliary(self, task, error):
            self.failed.append(error)

    class FakeMattingEngine:
        temporal_smoothing = 0
        edge_blur = 0

        def __init__(self, model):
            assert model == "birefnet-portrait"

        def process(self, source, work, progress):
            assert source.exists()
            progress(50, "segmenting")
            paths = [work / name for name in ("alpha.mp4", "poster.png", "white.mp4")]
            for path in paths:
                path.write_bytes(b"output")
            return SimpleNamespace(
                alpha_video=paths[0], poster_png=paths[1], white_preview=paths[2],
                fps=25.0, frame_count=12, width=640, height=480, model="birefnet-portrait",
                backend="test", foreground_recovery=False, foreground_recovered_ratio=0,
                green_screen=False, elapsed_seconds=1.0,
            )

    monkeypatch.setattr(remote_page_worker.RemotePageWorker, "_attempt_root", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(remote_page_worker, "PortraitMattingEngine", FakeMattingEngine)
    monkeypatch.setattr(
        remote_page_worker, "build_course_tts",
        lambda voice, ref_audio, course_settings, base: SimpleNamespace(provider=SimpleNamespace(release=lambda: None)),
    )

    def synthesize(_runtime, text, destination):
        assert text == "Hello"
        destination.write_bytes(b"wav")
        return destination

    monkeypatch.setattr(remote_page_worker, "synthesize_course_audio", synthesize)
    worker = remote_page_worker.RemotePageWorker.__new__(remote_page_worker.RemotePageWorker)
    worker.api = FakeApi()
    worker._current_task_id = None
    worker._last_error = None
    worker.process_auxiliary_task({
        "id": uuid4().hex, "kind": "avatar_matting", "lease_token": "test-token",
        "assets": [{"id": "master", "name": "master.mp4"}],
        "payload": {"source_asset_id": "master", "model": "birefnet-portrait"},
    })
    worker.process_auxiliary_task({
        "id": uuid4().hex, "kind": "speech_preview", "lease_token": "test-token",
        "assets": [{"id": "reference", "name": "reference.wav"}],
        "payload": {
            "reference_asset_id": "reference", "text": "Hello", "course_settings": {},
            "voice": {"id": "voice", "provider": "cosyvoice", "transcript": "hello", "settings": {}},
        },
    })
    assert not worker.api.failed
    assert [item[0] for item in worker.api.completed] == ["avatar_matting", "speech_preview"]
    assert worker.api.uploaded == ["alpha", "poster", "white", "audio"]
