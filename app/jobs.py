from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

from .engine import MuseTalkMLXEngine


@dataclass
class Job:
    id: str
    status: str = "queued"
    output: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobManager:
    """Serialize jobs because upstream build_video.py uses a shared temporary frame directory."""

    def __init__(self) -> None:
        self.engine = MuseTalkMLXEngine()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, video: Path, audio: Path, variant: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id)
        self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._execute,
            args=(job, video, audio, variant),
            daemon=True,
            name=f"avatar-{job_id}",
        )
        thread.start()
        return job

    def _execute(self, job: Job, video: Path, audio: Path, variant: str) -> None:
        with self._lock:
            job.status = "running"
            try:
                result = self.engine.render(video, audio, variant=variant, job_id=job.id)
                job.output = str(result.output)
                job.status = "completed"
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc()}"


manager = JobManager()
