from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

from .domain import JobStatus, RenderJob
from .queue import job_queue
from .settings import saas_settings
from .storage import object_store

log = logging.getLogger("digital-human.saas.worker")


class RenderHandler(Protocol):
    def render(self, job: RenderJob) -> Path: ...


class LocalMLXMuseTalkHandler:
    """Development handler that reuses the current Apple-Silicon engine.

    This keeps the SaaS control plane testable on a Mac. Linux GPU production
    workers will implement the same handler contract with MuseTalk CUDA.
    """

    def __init__(self) -> None:
        from ..engines import MuseTalkMLXEngine

        self.engine = MuseTalkMLXEngine()

    def render(self, job: RenderJob) -> Path:
        payload = job.payload
        video = payload.get("video")
        audio = payload.get("audio")
        if not video or not audio:
            raise ValueError("musetalk job requires payload.video and payload.audio")
        result = self.engine.render(
            video=Path(video),
            audio=Path(audio),
            variant=payload.get("variant"),
            job_id=job.id,
        )
        return Path(result.output)


def build_render_handler() -> RenderHandler:
    renderer = saas_settings.worker_backend.lower()
    if renderer in {"local", "mlx", "mlx-local"}:
        return LocalMLXMuseTalkHandler()
    if renderer == "redis":
        # Queue transport and render implementation are separate concerns. For
        # the first cloud milestone, Redis carries jobs while a GPU container
        # selects its renderer explicitly through SAAS_RENDERER.
        renderer = __import__("os").getenv("SAAS_RENDERER", "cuda-musetalk").lower()
    if renderer == "mlx-local":
        return LocalMLXMuseTalkHandler()
    raise RuntimeError(
        f"Renderer '{renderer}' is not installed in this worker image. "
        "Use SAAS_RENDERER=mlx-local for Mac development or install the CUDA worker adapter."
    )


def process_one(handler: RenderHandler) -> bool:
    job = job_queue.pop(timeout_seconds=saas_settings.worker_poll_timeout_seconds)
    if job is None:
        return False

    try:
        job.status = JobStatus.RUNNING
        job_queue.save(job)
        output = handler.render(job)
        key = f"{job.tenant_id}/{job.user_id}/{job.id}/{output.name}"
        job.output_uri = object_store.put_file(output, key)
        job.status = JobStatus.SUCCEEDED
        job.error = None
    except Exception as exc:  # noqa: BLE001
        log.exception("render job %s failed", job.id)
        job.status = JobStatus.FAILED
        job.error = str(exc)
    finally:
        job_queue.save(job)
    return True


def run_forever(handler: RenderHandler | None = None) -> None:
    handler = handler or build_render_handler()
    log.info("SaaS worker started; queue=%s", saas_settings.queue_name)
    while True:
        processed = process_one(handler)
        if not processed:
            time.sleep(0.2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
