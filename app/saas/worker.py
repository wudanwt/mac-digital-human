from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from sqlalchemy import select

from ..composer import CourseComposer, media_duration
from ..config import settings
from ..ppt import PresentationParser, PPTRenderer
from ..tts import create_tts
from .database import SessionLocal
from .domain import JobStatus, RenderJob
from .models import Asset, Avatar, Course, RenderJobRecord, VoiceProfile
from .queue import job_queue
from .services import enforce_storage_limit, reconcile_render_seconds, refund_render_seconds
from .settings import saas_settings
from .storage import object_store

log = logging.getLogger("digital-human.saas.worker")


class RenderHandler(Protocol):
    def render(self, job: RenderJob, progress: Callable[[int, str], None] | None = None) -> Path: ...


def _asset(db, tenant_id: str, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    return db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))


def _materialize(asset: Asset, work: Path) -> Path:
    suffix = Path(asset.name).suffix or ".bin"
    target = work / "assets" / f"{asset.id}{suffix}"
    return object_store.materialize(asset.object_key, target)


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_ai_label(source: Path) -> Path:
    if not saas_settings.require_ai_label:
        return source
    target = source.with_name(f"{source.stem}-labeled{source.suffix}")
    label_file = source.with_name("ai-label.txt")
    label_file.write_text(saas_settings.ai_label_text, encoding="utf-8")
    label_path = str(label_file).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"drawtext=textfile='{label_path}':x=w-tw-24:y=h-th-24:"
        "fontcolor=white@0.88:fontsize=24:box=1:boxcolor=black@0.48:boxborderw=8"
    )
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            vf,
            "-metadata",
            "comment=AI-generated digital human content",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if saas_settings.is_production:
            raise RuntimeError(proc.stderr.strip() or "AI content labeling failed")
        log.warning("AI label step failed in development; using original output: %s", proc.stderr.strip())
        return source
    return target


class MockCourseHandler:
    """End-to-end queue/storage smoke renderer that needs no GPU or model."""

    def render(self, job: RenderJob, progress: Callable[[int, str], None] | None = None) -> Path:
        if job.engine != "mock":
            raise RuntimeError("Mock worker only accepts engine=mock jobs")
        work = settings.workspace_dir / "saas-workers" / job.id
        work.mkdir(parents=True, exist_ok=True)
        output = work / "result.mp4"
        if progress:
            progress(30, "mock_render")
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x111827:s=1280x720:d=2:r=25",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "mock ffmpeg render failed")
        if progress:
            progress(90, "mock_complete")
        return output


class LocalMLXCourseHandler:
    """Full SaaS course renderer using the existing Apple-Silicon production stack."""

    def __init__(self) -> None:
        from ..engines import MuseTalkMLXEngine

        self.avatar_engine = MuseTalkMLXEngine()
        self.composer = CourseComposer()

    def render(self, job: RenderJob, progress: Callable[[int, str], None] | None = None) -> Path:
        if job.engine != "musetalk":
            raise RuntimeError("MLX worker only accepts engine=musetalk jobs")
        with SessionLocal() as db:
            course = db.scalar(
                select(Course).where(
                    Course.id == job.payload.get("course_id"),
                    Course.tenant_id == job.tenant_id,
                )
            )
            if course is None:
                raise RuntimeError("course not found")
            avatar = (
                db.scalar(select(Avatar).where(Avatar.id == course.avatar_id, Avatar.tenant_id == job.tenant_id))
                if course.avatar_id else None
            )
            voice = (
                db.scalar(select(VoiceProfile).where(VoiceProfile.id == course.voice_profile_id, VoiceProfile.tenant_id == job.tenant_id))
                if course.voice_profile_id else None
            )
            ppt_asset = _asset(db, job.tenant_id, course.ppt_asset_id)
            if ppt_asset is None:
                raise RuntimeError("course PPT asset is required")
            if avatar is None or not avatar.master_video_asset_id:
                raise RuntimeError("MuseTalk course requires avatar master video")
            master_asset = _asset(db, job.tenant_id, avatar.master_video_asset_id)
            if master_asset is None:
                raise RuntimeError("avatar master video asset missing")
            ref_asset = _asset(db, job.tenant_id, voice.reference_asset_id) if voice and voice.reference_asset_id else None
            direct_audio = _asset(db, job.tenant_id, job.payload.get("audio_asset_id"))

        work = settings.workspace_dir / "saas-workers" / job.id
        slide_dir = work / "slides"
        audio_dir = work / "audio"
        avatar_dir = work / "avatars"
        segment_dir = work / "segments"
        for path in (slide_dir, audio_dir, avatar_dir, segment_dir):
            path.mkdir(parents=True, exist_ok=True)

        ppt_path = _materialize(ppt_asset, work)
        master_path = _materialize(master_asset, work)
        ref_path = _materialize(ref_asset, work) if ref_asset else None
        direct_audio_path = _materialize(direct_audio, work) if direct_audio else None

        if progress:
            progress(8, "ppt_parse")
        deck = PresentationParser.parse(ppt_path)
        PPTRenderer.render_deck(deck, slide_dir)
        script_entries = json.loads(course.script_json or "[]")
        script_map = {
            int(item.get("index", idx + 1)): item
            for idx, item in enumerate(script_entries)
            if isinstance(item, dict)
        }
        settings_payload = json.loads(course.settings_json or "{}")

        tts = None
        if voice and direct_audio_path is None:
            tts = create_tts(
                {
                    "provider": voice.provider,
                    "ref_audio": str(ref_path) if ref_path else None,
                    "ref_text": voice.transcript or None,
                    **json.loads(voice.settings_json or "{}"),
                },
                base=work,
            )
            readiness = tts.readiness()
            if not readiness.get("ready", False):
                raise RuntimeError("TTS provider is not ready: " + json.dumps(readiness, ensure_ascii=False))

        clips: list[Path] = []
        subtitles: list[tuple[float, float, str]] = []
        cursor = 0.0
        total = max(1, len(deck.slides))
        try:
            for pos, slide in enumerate(deck.slides, start=1):
                override = script_map.get(slide.index, {})
                narration = str(
                    override.get("narration")
                    or override.get("script")
                    or slide.narration
                    or slide.title
                    or f"第{slide.index}页"
                ).strip()
                layout = str(override.get("layout") or settings_payload.get("layout") or slide.layout or "pip")
                if progress:
                    progress(12 + int((pos - 1) / total * 70), f"slide_{slide.index}_tts")
                audio_path = audio_dir / f"{slide.index:03d}.wav"
                slide_audio_asset_id = override.get("audio_asset_id")
                if slide_audio_asset_id:
                    with SessionLocal() as db:
                        item = _asset(db, job.tenant_id, str(slide_audio_asset_id))
                    if item is None:
                        raise RuntimeError(f"audio asset missing for slide {slide.index}")
                    object_store.materialize(item.object_key, audio_path)
                elif direct_audio_path is not None and len(deck.slides) == 1:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(direct_audio_path), str(audio_path)],
                        check=True,
                        capture_output=True,
                    )
                elif tts is not None:
                    tts.synthesize(narration, audio_path)
                else:
                    raise RuntimeError("No TTS voice or per-slide audio is available")

                avatar_video: Path | None = None
                if layout != "full_slide":
                    if progress:
                        progress(18 + int((pos - 1) / total * 70), f"slide_{slide.index}_avatar")
                    result = self.avatar_engine.render(
                        video=master_path,
                        audio=audio_path,
                        job_id=f"{job.id}-slide-{slide.index}",
                    )
                    avatar_video = Path(result.output)

                slide_image = slide_dir / f"slide-{slide.index}.png"
                if not slide_image.exists():
                    alternatives = sorted(slide_dir.glob(f"*{slide.index}*.png"))
                    if alternatives:
                        slide_image = alternatives[0]
                target = segment_dir / f"{slide.index:03d}.mp4"
                self.composer.compose_segment_layout(
                    avatar_video=avatar_video,
                    audio=audio_path,
                    slide_image=slide_image,
                    layout=layout,
                    target=target,
                    pip_position=str(settings_payload.get("pip_position") or "bottom_right"),
                    pip_size=str(settings_payload.get("pip_size") or "medium"),
                    custom_bg=settings_payload.get("custom_bg"),
                    bg_blur=bool(settings_payload.get("bg_blur", False)),
                    pip_box=override.get("pip_box") or settings_payload.get("pip_box"),
                    ppt_box=override.get("ppt_box") or settings_payload.get("ppt_box"),
                )
                duration = media_duration(audio_path)
                subtitles.append((cursor, cursor + duration, narration))
                cursor += duration
                clips.append(target)

            if progress:
                progress(88, "concat")
            raw_output = work / "course.mp4"
            self.composer.concat(clips, raw_output, work / "concat")
            srt = work / "course.srt"
            lines: list[str] = []
            for index, (start, end, text) in enumerate(subtitles, start=1):
                lines.extend([str(index), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""])
            srt.write_text("\n".join(lines), encoding="utf-8")
            output = work / "result.mp4"
            if settings_payload.get("embed_subtitles", True):
                self.composer.embed_subtitles(raw_output, srt, output)
            else:
                output = raw_output
            if progress:
                progress(94, "postprocess")
            return output
        finally:
            if tts is not None:
                try:
                    tts.release()
                except Exception:
                    pass


def build_render_handler() -> RenderHandler:
    renderer = os.getenv("SAAS_RENDERER", "").strip().lower()
    if not renderer:
        renderer = "mlx-local" if saas_settings.worker_backend == "local" else "cuda-musetalk"
    if renderer in {"mock", "fake"}:
        return MockCourseHandler()
    if renderer in {"local", "mlx", "mlx-local"}:
        return LocalMLXCourseHandler()
    if renderer in {"cuda", "cuda-musetalk"}:
        raise RuntimeError(
            "CUDA worker is intentionally skipped in this phase. "
            "Use SAAS_RENDERER=mock for SaaS acceptance or mlx-local on Apple Silicon."
        )
    raise RuntimeError(f"Unknown SAAS_RENDERER: {renderer}")


def _update_record(job_id: str, **values) -> None:
    with SessionLocal() as db:
        record = db.get(RenderJobRecord, job_id)
        if record is None:
            return
        for key, value in values.items():
            if hasattr(record, key):
                setattr(record, key, value)
        db.commit()


def _record_is_canceled(job_id: str) -> bool:
    with SessionLocal() as db:
        record = db.get(RenderJobRecord, job_id)
        return record is None or record.status == "canceled"


def process_one(handler: RenderHandler) -> bool:
    job = job_queue.pop(timeout_seconds=saas_settings.worker_poll_timeout_seconds)
    if job is None:
        return False

    if _record_is_canceled(job.id) or job.status == JobStatus.CANCELED:
        job.status = JobStatus.CANCELED
        job_queue.save(job)
        job_queue.ack(job.id)
        return True

    started = time.time()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        record = db.get(RenderJobRecord, job.id)
        if record is None or record.status == "canceled":
            job.status = JobStatus.CANCELED
            job_queue.save(job)
            job_queue.ack(job.id)
            return True
        try:
            queue_wait = max(0.0, (now - record.created_at).total_seconds())
        except Exception:
            queue_wait = None
        record.status = "running"
        record.progress = 2
        record.stage = "starting"
        record.started_at = now
        record.queue_wait_seconds = queue_wait
        db.commit()

    job.status = JobStatus.RUNNING
    job_queue.save(job)
    job_queue.heartbeat(job.id)

    def progress(value: int, stage: str) -> None:
        if _record_is_canceled(job.id):
            raise RuntimeError("Render canceled")
        _update_record(job.id, progress=max(0, min(int(value), 99)), stage=stage)
        job_queue.heartbeat(job.id)

    try:
        output = handler.render(job, progress=progress)
        if _record_is_canceled(job.id):
            raise RuntimeError("Render canceled")
        labeled_output = _apply_ai_label(output)
        duration = None
        try:
            duration = media_duration(labeled_output)
        except Exception:
            pass
        enforce_size = labeled_output.stat().st_size

        with SessionLocal() as db:
            enforce_storage_limit(db, job.tenant_id, incoming_bytes=enforce_size)

        key = f"{job.tenant_id}/outputs/{job.id}/{labeled_output.name}"
        uri = object_store.put_file(labeled_output, key)
        elapsed = time.time() - started
        output_asset_id: str | None = None
        try:
            with SessionLocal() as db:
                record = db.get(RenderJobRecord, job.id)
                if record is None or record.status == "canceled":
                    object_store.delete(key)
                    job.status = JobStatus.CANCELED
                    job.error = "Render canceled"
                    return True

                asset = Asset(
                    tenant_id=record.tenant_id,
                    user_id=record.user_id,
                    kind="output",
                    name=f"{record.course_id or record.id}.mp4",
                    object_key=key,
                    uri=uri,
                    content_type="video/mp4",
                    size_bytes=enforce_size,
                    sha256=_sha256(labeled_output),
                    status="ready",
                )
                db.add(asset)
                db.flush()
                output_asset_id = asset.id

                record.status = "succeeded"
                record.progress = 100
                record.stage = "completed"
                record.output_uri = uri
                record.output_asset_id = asset.id
                record.video_seconds = duration
                record.gpu_seconds = elapsed
                record.completed_at = datetime.now(timezone.utc)
                reconcile_render_seconds(
                    db,
                    tenant_id=record.tenant_id,
                    user_id=record.user_id,
                    job_id=record.id,
                    reserved_seconds=record.estimated_seconds,
                    actual_seconds=duration,
                )
                if record.course_id:
                    course = db.get(Course, record.course_id)
                    if course and course.tenant_id == record.tenant_id:
                        course.status = "completed"
                        course.output_asset_id = asset.id
                db.commit()
        except Exception:
            if output_asset_id is None:
                try:
                    object_store.delete(key)
                except Exception:
                    pass
            raise

        job.output_uri = uri
        job.status = JobStatus.SUCCEEDED
        job.error = None
        job_queue.save(job)
    except Exception as exc:  # noqa: BLE001
        canceled = _record_is_canceled(job.id)
        if not canceled:
            log.exception("render job %s failed", job.id)
        job.status = JobStatus.CANCELED if canceled else JobStatus.FAILED
        job.error = "Render canceled" if canceled else str(exc)
        with SessionLocal() as db:
            record = db.get(RenderJobRecord, job.id)
            if record and record.status not in {"canceled", "succeeded"}:
                record.status = "failed"
                record.stage = "failed"
                record.error = str(exc)
                record.completed_at = datetime.now(timezone.utc)
                refund_render_seconds(
                    db,
                    tenant_id=record.tenant_id,
                    user_id=record.user_id,
                    job_id=record.id,
                    seconds=record.estimated_seconds,
                )
                if record.course_id:
                    course = db.get(Course, record.course_id)
                    if course:
                        course.status = "draft"
                db.commit()
    finally:
        job_queue.save(job)
        job_queue.ack(job.id)
    return True


def run_forever(handler: RenderHandler | None = None) -> None:
    handler = handler or build_render_handler()
    recovered = job_queue.recover_stale()
    log.info(
        "SaaS worker started; queue=%s renderer=%s recovered=%s",
        saas_settings.queue_name,
        handler.__class__.__name__,
        recovered,
    )
    last_recovery = time.monotonic()
    while True:
        processed = process_one(handler)
        if time.monotonic() - last_recovery >= 60:
            recovered = job_queue.recover_stale()
            if recovered:
                log.warning("Recovered %s stale render jobs", recovered)
            last_recovery = time.monotonic()
        if not processed:
            time.sleep(0.2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
