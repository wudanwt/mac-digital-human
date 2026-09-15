from __future__ import annotations

import json
import time
from collections import deque
from threading import Lock
from typing import Protocol

from .domain import JobStatus, RenderJob
from .settings import saas_settings


class JobQueue(Protocol):
    def enqueue(self, job: RenderJob) -> RenderJob: ...
    def get(self, job_id: str) -> RenderJob | None: ...
    def save(self, job: RenderJob) -> RenderJob: ...
    def pop(self, timeout_seconds: int = 5) -> RenderJob | None: ...
    def cancel(self, job_id: str) -> bool: ...
    def ack(self, job_id: str) -> None: ...
    def heartbeat(self, job_id: str) -> None: ...
    def recover_stale(self) -> int: ...


def _priority(job: RenderJob) -> int:
    try:
        return int(job.payload.get("priority", 0))
    except Exception:
        return 0


class InMemoryJobQueue:
    """Development fallback with the same cancellation/ack contract as Redis."""

    def __init__(self) -> None:
        self._jobs: dict[str, RenderJob] = {}
        self._pending: dict[str, deque[str]] = {
            "high": deque(),
            "normal": deque(),
            "low": deque(),
        }
        self._processing: dict[str, float] = {}
        self._lock = Lock()

    @staticmethod
    def _bucket(job: RenderJob) -> str:
        value = _priority(job)
        return "high" if value >= 50 else "normal" if value >= 10 else "low"

    def enqueue(self, job: RenderJob) -> RenderJob:
        with self._lock:
            self._jobs[job.id] = job
            self._pending[self._bucket(job)].append(job.id)
        return job

    def get(self, job_id: str) -> RenderJob | None:
        return self._jobs.get(job_id)

    def save(self, job: RenderJob) -> RenderJob:
        job.touch()
        self._jobs[job.id] = job
        return job

    def pop(self, timeout_seconds: int = 5) -> RenderJob | None:
        deadline = time.monotonic() + max(0, timeout_seconds)
        while True:
            with self._lock:
                for bucket in ("high", "normal", "low"):
                    if self._pending[bucket]:
                        job_id = self._pending[bucket].popleft()
                        self._processing[job_id] = time.time()
                        return self._jobs.get(job_id)
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = JobStatus.CANCELED
            job.touch()
            for queue in self._pending.values():
                try:
                    queue.remove(job_id)
                except ValueError:
                    pass
            return True

    def ack(self, job_id: str) -> None:
        with self._lock:
            self._processing.pop(job_id, None)

    def heartbeat(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._processing:
                self._processing[job_id] = time.time()

    def recover_stale(self) -> int:
        cutoff = time.time() - saas_settings.queue_stale_seconds
        recovered = 0
        with self._lock:
            stale = [job_id for job_id, started in self._processing.items() if started < cutoff]
            for job_id in stale:
                self._processing.pop(job_id, None)
                job = self._jobs.get(job_id)
                if job and job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
                    job.status = JobStatus.QUEUED
                    self._pending[self._bucket(job)].append(job_id)
                    recovered += 1
        return recovered


class RedisJobQueue:
    """Redis-backed FIFO priority queues with an atomic processing list and stale recovery."""

    def __init__(self, url: str, queue_name: str) -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Redis backend requires `pip install .[saas]`") from exc

        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.queue_name = queue_name
        self.job_prefix = f"{queue_name}:job:"
        self.pending_keys = (
            f"{queue_name}:high",
            f"{queue_name}:normal",
            f"{queue_name}:low",
        )
        self.processing_key = f"{queue_name}:processing"
        self.processing_started_key = f"{queue_name}:processing-started"

    def _key(self, job_id: str) -> str:
        return f"{self.job_prefix}{job_id}"

    def _pending_key(self, job: RenderJob) -> str:
        value = _priority(job)
        return self.pending_keys[0] if value >= 50 else self.pending_keys[1] if value >= 10 else self.pending_keys[2]

    def enqueue(self, job: RenderJob) -> RenderJob:
        pipe = self.client.pipeline(transaction=True)
        pipe.set(self._key(job.id), json.dumps(job.to_dict(), ensure_ascii=False))
        pipe.lpush(self._pending_key(job), job.id)
        pipe.execute()
        return job

    def get(self, job_id: str) -> RenderJob | None:
        raw = self.client.get(self._key(job_id))
        if raw is None:
            return None
        return RenderJob.from_dict(json.loads(raw))

    def save(self, job: RenderJob) -> RenderJob:
        job.touch()
        self.client.set(self._key(job.id), json.dumps(job.to_dict(), ensure_ascii=False))
        return job

    def pop(self, timeout_seconds: int = 5) -> RenderJob | None:
        deadline = time.monotonic() + max(0, timeout_seconds)
        while True:
            for source in self.pending_keys:
                job_id = self.client.rpoplpush(source, self.processing_key)
                if not job_id:
                    continue
                self.client.hset(self.processing_started_key, job_id, str(time.time()))
                job = self.get(job_id)
                if job is not None:
                    return job
                self.ack(job_id)
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.1)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.CANCELED
        self.save(job)
        pipe = self.client.pipeline(transaction=True)
        for key in self.pending_keys:
            pipe.lrem(key, 0, job_id)
        # If it was claimed but has not started yet, the worker will also verify DB state before rendering.
        pipe.lrem(self.processing_key, 0, job_id)
        pipe.hdel(self.processing_started_key, job_id)
        pipe.execute()
        return True

    def ack(self, job_id: str) -> None:
        pipe = self.client.pipeline(transaction=True)
        pipe.lrem(self.processing_key, 1, job_id)
        pipe.hdel(self.processing_started_key, job_id)
        pipe.execute()

    def heartbeat(self, job_id: str) -> None:
        self.client.hset(self.processing_started_key, job_id, str(time.time()))

    def recover_stale(self) -> int:
        cutoff = time.time() - saas_settings.queue_stale_seconds
        recovered = 0
        for job_id in self.client.lrange(self.processing_key, 0, -1):
            raw = self.client.hget(self.processing_started_key, job_id)
            try:
                started = float(raw or 0)
            except ValueError:
                started = 0
            if started and started >= cutoff:
                continue
            job = self.get(job_id)
            pipe = self.client.pipeline(transaction=True)
            pipe.lrem(self.processing_key, 1, job_id)
            pipe.hdel(self.processing_started_key, job_id)
            if job and job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}:
                job.status = JobStatus.QUEUED
                job.touch()
                pipe.set(self._key(job.id), json.dumps(job.to_dict(), ensure_ascii=False))
                pipe.lpush(self._pending_key(job), job.id)
                recovered += 1
            pipe.execute()
        return recovered


def build_job_queue() -> JobQueue:
    if saas_settings.worker_backend == "redis":
        return RedisJobQueue(saas_settings.redis_url, saas_settings.queue_name)
    if saas_settings.is_production and not saas_settings.allow_local_fallback:
        raise RuntimeError("Production SaaS requires WORKER_BACKEND=redis")
    return InMemoryJobQueue()


job_queue = build_job_queue()
