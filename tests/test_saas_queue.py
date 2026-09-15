import time

from app.saas.domain import JobStatus, RenderJob
from app.saas.queue import InMemoryJobQueue


def _job(job_id: str, priority: int = 0) -> RenderJob:
    return RenderJob(
        id=job_id,
        tenant_id="tenant-a",
        user_id="user-a",
        engine="musetalk",
        payload={"priority": priority},
    )


def test_in_memory_queue_round_trip() -> None:
    queue = InMemoryJobQueue()
    job = _job("round-trip")
    queue.enqueue(job)
    popped = queue.pop(timeout_seconds=0)
    assert popped is not None
    assert popped.id == job.id
    assert popped.tenant_id == "tenant-a"
    assert popped.status == JobStatus.QUEUED
    queue.ack(job.id)


def test_queue_saves_status_changes() -> None:
    queue = InMemoryJobQueue()
    job = _job("save")
    queue.enqueue(job)
    job.status = JobStatus.RUNNING
    queue.save(job)
    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == JobStatus.RUNNING


def test_priority_queue_prefers_business_then_pro_then_free() -> None:
    queue = InMemoryJobQueue()
    queue.enqueue(_job("free", 0))
    queue.enqueue(_job("pro", 10))
    queue.enqueue(_job("business", 50))
    assert queue.pop(timeout_seconds=0).id == "business"
    assert queue.pop(timeout_seconds=0).id == "pro"
    assert queue.pop(timeout_seconds=0).id == "free"


def test_cancel_removes_pending_job() -> None:
    queue = InMemoryJobQueue()
    job = _job("cancel")
    queue.enqueue(job)
    assert queue.cancel(job.id) is True
    assert queue.get(job.id).status == JobStatus.CANCELED
    assert queue.pop(timeout_seconds=0) is None


def test_recover_stale_requeues_claimed_job() -> None:
    queue = InMemoryJobQueue()
    job = _job("stale")
    queue.enqueue(job)
    popped = queue.pop(timeout_seconds=0)
    assert popped is not None
    queue._processing[job.id] = time.time() - 100_000  # noqa: SLF001 - deterministic queue recovery test
    assert queue.recover_stale() == 1
    recovered = queue.pop(timeout_seconds=0)
    assert recovered is not None
    assert recovered.id == job.id
    assert recovered.status == JobStatus.QUEUED
