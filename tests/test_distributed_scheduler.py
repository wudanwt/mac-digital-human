from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.saas.database import SessionLocal
from app.saas.distributed_render_models import RenderSubtask, WorkerNode
from app.saas.distributed_scheduler import (
    LeaseConflict,
    claim_page_task,
    complete_page_task,
    initialize_parent_graph,
    publish_prepared_pages,
    renew_lease,
    report_progress,
)
from app.saas.settings import saas_settings
from app.saas_main import app


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/saas/auth/register",
        json={
            "email": f"scheduler-{uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "scheduler",
            "workspace_name": "scheduler workspace",
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


def _queued_parent(client: TestClient, token: str) -> str:
    ppt = _upload(client, token, "scheduler.pptx", "ppt", b"ppt")
    master = _upload(client, token, "scheduler.mp4", "video", b"video")
    audio = _upload(client, token, "scheduler.wav", "audio", b"audio")
    voice = client.post(
        "/api/saas/voices",
        headers=_headers(token),
        json={
            "name": "Scheduler Voice",
            "provider": "cosyvoice",
            "reference_asset_id": audio["id"],
            "transcript": "参考逐字稿",
            "consent_confirmed": True,
        },
    ).json()
    avatar = client.post(
        "/api/saas/avatars",
        headers=_headers(token),
        json={
            "name": "Scheduler Avatar",
            "master_video_asset_id": master["id"],
            "voice_profile_id": voice["id"],
            "consent_confirmed": True,
        },
    ).json()
    course_response = client.post(
        "/api/saas/courses",
        headers=_headers(token),
        json={
            "title": "Distributed scheduler test",
            "ppt_asset_id": ppt["id"],
            "avatar_id": avatar["id"],
            "voice_profile_id": voice["id"],
            "script": [{"index": 1, "narration": "one"}],
        },
    )
    assert course_response.status_code == 201, course_response.text
    render = client.post(
        f"/api/saas/courses/{course_response.json()['id']}/render",
        headers=_headers(token),
        json={"engine": "mock", "estimated_seconds": 1, "audio_asset_id": audio["id"]},
    )
    assert render.status_code == 202, render.text
    return render.json()["id"]


def test_page_leases_are_exclusive_and_release_finalize_after_last_page() -> None:
    with TestClient(app) as client:
        token = _register(client)
        parent_job_id = _queued_parent(client, token)

        with SessionLocal() as db:
            first_prepare, first_finalize = initialize_parent_graph(db, parent_job_id)
            second_prepare, second_finalize = initialize_parent_graph(db, parent_job_id)
            assert first_prepare.id == second_prepare.id
            assert first_finalize.id == second_finalize.id
            assert db.scalar(
                select(func.count()).select_from(RenderSubtask).where(RenderSubtask.parent_job_id == parent_job_id)
            ) == 2

            pages = publish_prepared_pages(
                db,
                parent_job_id=parent_job_id,
                pages=[
                    {"index": 1, "narration": "short page", "estimated_seconds": 5},
                    {"index": 2, "narration": "the longest page", "estimated_seconds": 30},
                    {"index": 3, "narration": "medium page", "estimated_seconds": 15},
                ],
                prepared_manifest={"page_count": 3},
            )
            assert [page.slide_index for page in pages] == [1, 2, 3]
            node = WorkerNode(
                name="mini-test",
                credential_hash=f"test-{uuid4().hex}",
                status="online",
                accepting_tasks=True,
                slots_total=1,
                slots_busy=0,
                render_contract_version=saas_settings.render_contract_version,
            )
            db.add(node)
            db.commit()
            node_id = node.id

        # Authentication may load the node before a concurrent claim commits.
        # The locked claim query must refresh that stale identity-map value.
        with SessionLocal() as stale_db:
            stale_node = stale_db.get(WorkerNode, node_id)
            assert stale_node is not None and stale_node.slots_busy == 0
            with SessionLocal() as other_db:
                busy_node = other_db.get(WorkerNode, node_id)
                assert busy_node is not None
                busy_node.slots_busy = 1
                other_db.commit()
            assert claim_page_task(stale_db, node_id=node_id) is None
        with SessionLocal() as db:
            node = db.get(WorkerNode, node_id)
            assert node is not None
            node.slots_busy = 0
            db.commit()

        completed: list[int] = []
        for expected_index in (2, 3, 1):
            with SessionLocal() as db:
                lease = claim_page_task(db, node_id=node_id)
                assert lease is not None
                assert lease.slide_index == expected_index
                # A one-slot node cannot take another page until it reports this
                # attempt complete, even when many pages remain queued.
                assert claim_page_task(db, node_id=node_id) is None
                with pytest.raises(LeaseConflict):
                    report_progress(
                        db,
                        task_id=lease.task_id,
                        attempt_id=lease.attempt_id,
                        node_id=node_id,
                        lease_token="wrong-token",
                        progress=25,
                        stage="tts",
                    )
                renewed = renew_lease(
                    db,
                    task_id=lease.task_id,
                    attempt_id=lease.attempt_id,
                    node_id=node_id,
                    lease_token=lease.lease_token,
                )
                assert renewed >= lease.lease_expires_at
                report_progress(
                    db,
                    task_id=lease.task_id,
                    attempt_id=lease.attempt_id,
                    node_id=node_id,
                    lease_token=lease.lease_token,
                    progress=80,
                    stage="compose",
                    metrics={"rss_mb": 9000},
                )
                queued_finalize = complete_page_task(
                    db,
                    task_id=lease.task_id,
                    attempt_id=lease.attempt_id,
                    node_id=node_id,
                    lease_token=lease.lease_token,
                    metrics={"duration": 10.0},
                )
                completed.append(expected_index)
                assert queued_finalize is (len(completed) == 3)
                with pytest.raises(LeaseConflict):
                    complete_page_task(
                        db,
                        task_id=lease.task_id,
                        attempt_id=lease.attempt_id,
                        node_id=node_id,
                        lease_token=lease.lease_token,
                    )
                db.commit()

        with SessionLocal() as db:
            finalize = db.scalar(
                select(RenderSubtask).where(
                    RenderSubtask.parent_job_id == parent_job_id,
                    RenderSubtask.task_type == "finalize",
                )
            )
            assert finalize is not None
            assert finalize.status == "queued"
            assert finalize.stage == "queued"
