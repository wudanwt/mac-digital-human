from app.saas.domain import JobStatus, RenderJob
from app.saas.queue import InMemoryJobQueue


def test_in_memory_queue_round_trip() -> None:
    queue = InMemoryJobQueue()
    job = RenderJob(
        tenant_id="tenant-a",
        user_id="user-a",
        engine="musetalk",
        payload={"video": "master.mp4", "audio": "voice.wav"},
    )

    queue.enqueue(job)
    popped = queue.pop()

    assert popped is not None
    assert popped.id == job.id
    assert popped.tenant_id == "tenant-a"
    assert popped.status == JobStatus.QUEUED


def test_queue_saves_status_changes() -> None:
    queue = InMemoryJobQueue()
    job = RenderJob(
        tenant_id="tenant-a",
        user_id="user-a",
        engine="musetalk",
        payload={},
    )
    queue.enqueue(job)

    job.status = JobStatus.RUNNING
    queue.save(job)

    stored = queue.get(job.id)
    assert stored is not None
    assert stored.status == JobStatus.RUNNING
