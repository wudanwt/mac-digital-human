from __future__ import annotations

import json
from collections import deque
from threading import Lock
from typing import Protocol

from .domain import RenderJob
from .settings import saas_settings


class JobQueue(Protocol):
    def enqueue(self, job: RenderJob) -> RenderJob: ...
    def get(self, job_id: str) -> RenderJob | None: ...
    def save(self, job: RenderJob) -> RenderJob: ...
    def pop(self, timeout_seconds: int = 5) -> RenderJob | None: ...


class InMemoryJobQueue:
    """Development fallback. Production must use a shared queue backend."""

    def __init__(self) -> None:
        self._jobs: dict[str, RenderJob] = {}
        self._pending: deque[str] = deque()
        self._lock = Lock()

    def enqueue(self, job: RenderJob) -> RenderJob:
        with self._lock:
            self._jobs[job.id] = job
            self._pending.append(job.id)
        return job

    def get(self, job_id: str) -> RenderJob | None:
        return self._jobs.get(job_id)

    def save(self, job: RenderJob) -> RenderJob:
        job.touch()
        self._jobs[job.id] = job
        return job

    def pop(self, timeout_seconds: int = 5) -> RenderJob | None:
        del timeout_seconds
        with self._lock:
            if not self._pending:
                return None
            job_id = self._pending.popleft()
        return self._jobs.get(job_id)


class RedisJobQueue:
    """Redis-backed queue and job state store shared by API and GPU workers."""

    def __init__(self, url: str, queue_name: str) -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - optional SaaS dependency
            raise RuntimeError("Redis backend requires `pip install .[saas]`") from exc

        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.queue_name = queue_name
        self.job_prefix = f"{queue_name}:job:"

    def _key(self, job_id: str) -> str:
        return f"{self.job_prefix}{job_id}"

    def enqueue(self, job: RenderJob) -> RenderJob:
        pipe = self.client.pipeline(transaction=True)
        pipe.set(self._key(job.id), json.dumps(job.to_dict(), ensure_ascii=False))
        pipe.rpush(self.queue_name, job.id)
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
        item = self.client.blpop(self.queue_name, timeout=timeout_seconds)
        if item is None:
            return None
        _, job_id = item
        return self.get(job_id)


def build_job_queue() -> JobQueue:
    if saas_settings.worker_backend == "redis":
        return RedisJobQueue(saas_settings.redis_url, saas_settings.queue_name)
    if saas_settings.is_production and not saas_settings.allow_local_fallback:
        raise RuntimeError("Production SaaS requires WORKER_BACKEND=redis")
    return InMemoryJobQueue()


job_queue = build_job_queue()
