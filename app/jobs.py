from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .engines import LongCatMLXEngine, MuseTalkMLXEngine


@dataclass
class Job:
    id: str
    engine: str
    status: str = "queued"
    output: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobManager:
    """Serialize heavy generation jobs on a single Apple Silicon machine.

    MuseTalk's upstream pipeline uses shared temporary paths, while LongCat can
    consume most of a 48 GB unified-memory Mac. A single queue is therefore the
    safest default for both engines.
    """

    def __init__(self) -> None:
        self.engines = {
            "musetalk": MuseTalkMLXEngine(),
            "longcat": LongCatMLXEngine(),
        }
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    @property
    def engine(self) -> MuseTalkMLXEngine:
        """Compatibility alias for the original MuseTalk-only API."""
        return self.engines["musetalk"]

    def readiness(self) -> dict:
        return {name: engine.readiness() for name, engine in self.engines.items()}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, engine: str, **kwargs: Any) -> Job:
        if engine not in self.engines:
            raise ValueError(f"unknown engine: {engine}")

        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, engine=engine)
        self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._execute,
            args=(job, kwargs),
            daemon=True,
            name=f"avatar-{engine}-{job_id}",
        )
        thread.start()
        return job

    def _execute(self, job: Job, kwargs: dict[str, Any]) -> None:
        with self._lock:
            job.status = "running"
            try:
                result = self.engines[job.engine].render(job_id=job.id, **kwargs)
                job.output = str(result.output)
                job.status = "completed"
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc()}"


manager = JobManager()
