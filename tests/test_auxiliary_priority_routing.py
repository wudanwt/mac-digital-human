from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.saas.auxiliary_task_models import AuxiliaryTaskLease
from app.saas.avatar_matting_models import AvatarMattingJob
from app.saas.database import SessionLocal, get_db
from app.saas.distributed_render_models import WorkerNode
from app.saas_main import app
from app.saas.models import Asset, Avatar, Course, Tenant, User, VoiceProfile
from app.saas.distributed_scheduler import hash_secret
from app.saas.settings import saas_settings
from app.saas.speech_preview_models import SpeechPreviewJob
from app.saas.speech_preview_service import synthesis_fingerprint
from app.saas.storage import object_store


def test_auxiliary_priority_routing() -> None:
    original_enabled = saas_settings.distributed_render_enabled
    object.__setattr__(saas_settings, "distributed_render_enabled", True)
    try:
        with TestClient(app) as client:
            suffix = uuid4().hex
            pref_token = f"pref-{suffix}"
            fallback_token = f"fallback-{suffix}"
            now = datetime.now(timezone.utc)

            with SessionLocal() as db:
                db.query(SpeechPreviewJob).filter(SpeechPreviewJob.status == "queued").update(
                    {"status": "failed", "error": "test setup cleanup"}
                )
                db.query(AvatarMattingJob).filter(AvatarMattingJob.status == "queued").update(
                    {"status": "failed", "error": "test setup cleanup"}
                )
                db.commit()

                user = User(email=f"prio-{suffix}@example.com", password_hash="test")
                db.add(user)
                db.flush()
                tenant = Tenant(name="Prio test", slug=f"prio-{suffix}", owner_user_id=user.id)
                db.add(tenant)
                db.flush()

                ref_bytes = b"test-audio-content"
                ref_key = f"{tenant.id}/prio-reference-{suffix}.wav"
                reference = Asset(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    kind="audio",
                    name="reference.wav",
                    object_key=ref_key,
                    uri=object_store.put_stream(BytesIO(ref_bytes), ref_key),
                    content_type="audio/wav",
                    size_bytes=len(ref_bytes),
                    sha256=hashlib.sha256(ref_bytes).hexdigest(),
                    status="ready",
                )
                db.add(reference)
                db.flush()

                voice = VoiceProfile(
                    tenant_id=tenant.id, name="prio-voice", reference_asset_id=reference.id, transcript="test"
                )
                course = Course(tenant_id=tenant.id, user_id=user.id, title="prio-course", settings_json="{}")
                db.add_all([voice, course])
                db.flush()
                db.refresh(voice)

                # Preferred node (e.g. M5 Pro)
                pref_node = WorkerNode(
                    name="macbook-preferred",
                    credential_hash=hash_secret(pref_token),
                    status="online",
                    accepting_tasks=True,
                    slots_total=1,
                    slots_busy=0,
                    capabilities_json=json.dumps(["musetalk", "speech-preview", "portrait-matting", "aux-routing:preferred"]),
                    last_seen_at=now,
                )
                # Normal node (e.g. m4-mini-ergou)
                normal_node = WorkerNode(
                    name="m4-mini-normal",
                    credential_hash=hash_secret(fallback_token),
                    status="online",
                    accepting_tasks=True,
                    slots_total=1,
                    slots_busy=0,
                    capabilities_json=json.dumps(["musetalk", "speech-preview", "portrait-matting"]),
                    last_seen_at=now,
                )
                db.add_all([pref_node, normal_node])
                db.commit()

                # Create a fresh speech preview job (age 0 seconds)
                job = SpeechPreviewJob(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    course_id=course.id,
                    voice_profile_id=voice.id,
                    slide_index=1,
                    scope="selection",
                    text="Priority test",
                    text_hash=synthesis_fingerprint(
                        text="Priority test", scope="selection", voice=voice, course_settings={}
                    ),
                    status="queued",
                    created_at=now,
                )
                db.add(job)
                db.commit()
                job_id = job.id

            normal_headers = {"Authorization": f"Bearer {fallback_token}"}
            pref_headers = {"Authorization": f"Bearer {pref_token}"}

            # 1. Normal worker tries to claim fresh job while preferred worker is online -> must get None
            claim_normal = client.post("/api/saas/internal/render/aux/claim", headers=normal_headers)
            assert claim_normal.status_code == 200
            assert claim_normal.json()["task"] is None, "Normal worker should NOT steal fresh job from available preferred worker"

            # 2. Preferred worker claims fresh job -> must succeed!
            claim_pref = client.post("/api/saas/internal/render/aux/claim", headers=pref_headers)
            assert claim_pref.status_code == 200
            task_pref = claim_pref.json()["task"]
            assert task_pref is not None
            assert task_pref["job_id"] == job_id
            assert task_pref["kind"] == "speech_preview"

            # Clean up preferred lease for test continuation
            with SessionLocal() as db:
                lease = db.get(AuxiliaryTaskLease, task_pref["id"])
                job = db.get(SpeechPreviewJob, job_id)
                job.status = "queued"
                p_node = db.get(WorkerNode, pref_node.id)
                p_node.slots_busy = 0
                p_node.status = "online"
                p_node.current_task_id = None
                db.delete(lease)
                db.commit()

            # 3. Now make job older than fallback seconds (e.g. 10s old)
            with SessionLocal() as db:
                job = db.get(SpeechPreviewJob, job_id)
                job.created_at = datetime.now(timezone.utc) - timedelta(seconds=12)
                db.commit()

            # Normal worker tries to claim expired fallback window -> must succeed!
            claim_fallback = client.post("/api/saas/internal/render/aux/claim", headers=normal_headers)
            assert claim_fallback.status_code == 200
            task_fallback = claim_fallback.json()["task"]
            assert task_fallback is not None
            assert task_fallback["job_id"] == job_id
    finally:
        object.__setattr__(saas_settings, "distributed_render_enabled", original_enabled)
