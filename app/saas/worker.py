from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from sqlalchemy import select

from ..composer import CourseComposer, media_duration
from ..config import settings
from ..ppt import PresentationParser, PPTRenderer
from ..subtitles import SubtitleItem, SubtitlesGenerator
from .database import SessionLocal
from .domain import JobStatus, RenderJob
from .models import Asset, Avatar, Course, RenderJobRecord, VoiceProfile
from .queue import job_queue
from .services import enforce_storage_limit, reconcile_render_seconds, refund_render_seconds
from .settings import saas_settings
from .storage import object_store
from .tts_pipeline import build_course_tts, normalize_external_audio, synthesize_course_audio

log = logging.getLogger("digital-human.saas.worker")
ProgressCallback = Callable[[int, str, dict[str, Any] | None], None]


class RenderHandler(Protocol):
    def render(self, job: RenderJob, progress: ProgressCallback | None = None) -> Path: ...


def _asset(db, tenant_id: str, asset_id: str | None) -> Asset | None:
    if not asset_id:
        return None
    return db.scalar(select(Asset).where(Asset.id == asset_id, Asset.tenant_id == tenant_id))


def _materialize(asset: Asset, work: Path) -> Path:
    suffix = Path(asset.name).suffix or ".bin"
    target = work / "assets" / f"{asset.id}{suffix}"
    return object_store.materialize(asset.object_key, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_file() -> str | None:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    return next((item for item in candidates if Path(item).exists()), None)


def _preferred_h264_encoder() -> str:
    if os.getenv("SAAS_FORCE_LIBX264", "").strip().lower() in {"1", "true", "yes", "on"}:
        return "libx264"
    if os.uname().sysname == "Darwin":
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
        if probe.returncode == 0 and "h264_videotoolbox" in probe.stdout:
            return "h264_videotoolbox"
    return "libx264"


def _apply_ai_label(source: Path) -> Path:
    """Apply a visible AI badge without relying on FFmpeg's optional drawtext filter.

    Homebrew/third-party FFmpeg builds may omit ``drawtext``.  We render the badge
    with Pillow and use the universally available overlay filter instead.  Audio
    and an existing mov_text subtitle stream are preserved.
    """
    if not saas_settings.require_ai_label:
        return source

    from PIL import Image, ImageDraw, ImageFont

    target = source.with_name(f"{source.stem}-labeled{source.suffix}")
    badge = source.with_name("ai-generated-badge.png")
    text = saas_settings.ai_label_text.strip() or "AI生成"
    font_path = _font_file()
    try:
        font = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    card = Image.new("RGBA", (tw + 28, th + 18), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card)
    card_draw.rounded_rectangle(
        [0, 0, card.width - 1, card.height - 1],
        radius=10,
        fill=(6, 12, 20, 178),
        outline=(255, 255, 255, 46),
        width=1,
    )
    card_draw.text((14, 9 - bbox[1]), text, font=font, fill=(255, 255, 255, 232))
    card.save(badge)

    duration = media_duration(source)
    encoder = _preferred_h264_encoder()
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source), "-loop", "1", "-framerate", "1", "-i", str(badge),
        "-filter_complex", "[0:v:0][1:v:0]overlay=W-w-24:H-h-24:format=auto[v]",
        "-map", "[v]", "-map", "0:a?", "-map", "0:s?",
    ]
    if encoder == "h264_videotoolbox":
        command.extend(["-c:v", encoder, "-b:v", "8M"])
    else:
        command.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"])
    command.extend(
        [
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-c:s", "copy",
            "-metadata", "comment=AI-generated digital human content",
            "-t", f"{duration:.3f}", "-movflags", "+faststart", str(target),
        ]
    )
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        if saas_settings.is_production:
            raise RuntimeError(proc.stderr.strip() or "AI content labeling failed")
        log.warning("AI label overlay failed in development; using original output: %s", proc.stderr.strip())
        return source
    return target


def _copy_runtime(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False))


class MockCourseHandler:
    """End-to-end queue/storage smoke renderer that needs no GPU or model."""

    def render(self, job: RenderJob, progress: ProgressCallback | None = None) -> Path:
        if job.engine != "mock":
            raise RuntimeError("Mock worker only accepts engine=mock jobs")
        work = settings.workspace_dir / "saas-workers" / job.id
        work.mkdir(parents=True, exist_ok=True)
        output = work / "result.mp4"
        if progress:
            progress(30, "mock_render", {"stage": 3, "stage_name": "Mock 渲染", "step_detail": "正在生成验收视频"})
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
            progress(90, "mock_complete", {"stage": 4, "stage_name": "后处理", "step_detail": "Mock 视频生成完成"})
        return output


class LocalMLXCourseHandler:
    """Full SaaS course renderer using the existing Apple-Silicon production stack."""

    def __init__(self) -> None:
        from ..engines import MuseTalkMLXEngine

        self.avatar_engine = MuseTalkMLXEngine()
        self.composer = CourseComposer()

    def render(self, job: RenderJob, progress: ProgressCallback | None = None) -> Path:
        if job.engine != "musetalk":
            raise RuntimeError("MLX worker only accepts engine=musetalk jobs")

        render_started = time.time()
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
            voice_id = course.voice_profile_id or (avatar.voice_profile_id if avatar else None)
            voice = (
                db.scalar(select(VoiceProfile).where(VoiceProfile.id == voice_id, VoiceProfile.tenant_id == job.tenant_id))
                if voice_id else None
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
            script_entries = json.loads(course.script_json or "[]")
            settings_payload = json.loads(course.settings_json or "{}")

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

        deck = PresentationParser.parse(ppt_path)
        total = max(1, len(deck.slides))
        script_map = {
            int(item.get("index", idx + 1)): item
            for idx, item in enumerate(script_entries)
            if isinstance(item, dict)
        }
        runtime: dict[str, Any] = {
            "stage": 1,
            "stage_name": "课件解析与底板生成",
            "current_slide": 0,
            "total_slides": len(deck.slides),
            "step_detail": "准备渲染高清幻灯片底板",
            "elapsed_seconds": 0.0,
            "eta_seconds": None,
            "tts_prefetch": os.getenv("SAAS_TTS_PREFETCH", "1").strip().lower() not in {"0", "false", "no", "off"},
            "slides": {
                str(slide.index): {
                    "index": slide.index,
                    "title": slide.title,
                    "audio": "pending",
                    "video": "pending",
                    "compose": "pending",
                    "audio_seconds": None,
                    "render_seconds": None,
                }
                for slide in deck.slides
            },
        }

        def emit(value: int, stage_slug: str, *, stage: int, stage_name: str, current_slide: int = 0, detail: str) -> None:
            elapsed = time.time() - render_started
            eta = None
            if 1 <= value < 100 and elapsed > 2:
                eta = max(0.0, elapsed * (100 - value) / value)
            runtime.update(
                {
                    "stage": stage,
                    "stage_name": stage_name,
                    "current_slide": current_slide,
                    "step_detail": detail,
                    "elapsed_seconds": round(elapsed, 1),
                    "eta_seconds": round(eta, 0) if eta is not None else None,
                }
            )
            if progress:
                progress(value, stage_slug, _copy_runtime(runtime))

        emit(6, "ppt_parse", stage=1, stage_name="课件解析与底板生成", detail=f"正在渲染 {len(deck.slides)} 页 PPT")
        PPTRenderer.render_deck(deck, slide_dir)
        emit(10, "ppt_ready", stage=1, stage_name="课件解析与底板生成", detail="PPT 底板已就绪")

        tts_runtime = None
        if voice and direct_audio_path is None:
            tts_runtime = build_course_tts(
                voice,
                ref_audio=ref_path,
                course_settings=settings_payload,
                base=work,
            )

        plans: list[dict[str, Any]] = []
        for slide in deck.slides:
            override = script_map.get(slide.index, {})
            narration = str(
                override.get("narration")
                or override.get("script")
                or slide.narration
                or slide.title
                or f"第{slide.index}页"
            ).strip()
            plans.append(
                {
                    "slide": slide,
                    "override": override,
                    "narration": narration,
                    "layout": str(override.get("layout") or settings_payload.get("layout") or slide.layout or "pip"),
                }
            )

        def make_audio(plan: dict[str, Any]) -> Path:
            slide = plan["slide"]
            override = plan["override"]
            target = audio_dir / f"{slide.index:03d}.wav"
            slide_audio_asset_id = override.get("audio_asset_id")
            if slide_audio_asset_id:
                with SessionLocal() as db:
                    item = _asset(db, job.tenant_id, str(slide_audio_asset_id))
                    if item is None:
                        raise RuntimeError(f"audio asset missing for slide {slide.index}")
                    source = _materialize(item, work)
                return normalize_external_audio(source, target)
            if direct_audio_path is not None and len(plans) == 1:
                return normalize_external_audio(direct_audio_path, target)
            if tts_runtime is None:
                raise RuntimeError("No TTS voice or per-slide audio is available")
            return synthesize_course_audio(tts_runtime, plan["narration"], target)

        clips: list[Path] = []
        subtitle_items: list[SubtitleItem] = []
        cursor = 0.0
        subtitle_index = 1
        prefetch_enabled = bool(runtime["tts_prefetch"]) and len(plans) > 1
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="saas-tts") if prefetch_enabled else None
        audio_future: Future[Path] | None = executor.submit(make_audio, plans[0]) if executor and plans else None

        try:
            for pos, plan in enumerate(plans, start=1):
                slide = plan["slide"]
                override = plan["override"]
                slide_state = runtime["slides"][str(slide.index)]
                slide_state["audio"] = "running"
                emit(
                    10 + int((pos - 1) / total * 70),
                    f"slide_{slide.index}_tts",
                    stage=2,
                    stage_name="逐页高保真语音合成",
                    current_slide=slide.index,
                    detail=f"正在生成第 {slide.index} 页语音（{len(plan['narration'])} 字）",
                )
                audio_started = time.time()
                if audio_future is not None:
                    audio_path = audio_future.result()
                else:
                    audio_path = make_audio(plan)
                duration = media_duration(audio_path)
                slide_state["audio"] = "done"
                slide_state["audio_seconds"] = round(duration, 2)
                slide_state["tts_elapsed_seconds"] = round(time.time() - audio_started, 2)

                # Start page N+1 TTS immediately before page N enters the much
                # longer MuseTalk GPU step.  This hides most per-page TTS latency.
                next_future: Future[Path] | None = None
                if executor and pos < len(plans):
                    next_future = executor.submit(make_audio, plans[pos])

                layout = plan["layout"]
                avatar_video: Path | None = None
                if layout != "full_slide":
                    slide_state["video"] = "running"
                    emit(
                        18 + int((pos - 1) / total * 70),
                        f"slide_{slide.index}_avatar",
                        stage=3,
                        stage_name="数字人视频渲染",
                        current_slide=slide.index,
                        detail=f"正在生成第 {slide.index} 页数字人口型（音频 {duration:.1f}s）",
                    )
                    video_started = time.time()
                    result = self.avatar_engine.render(
                        video=master_path,
                        audio=audio_path,
                        job_id=f"{job.id}-slide-{slide.index}",
                    )
                    avatar_video = Path(result.output)
                    slide_state["video"] = "done"
                    slide_state["render_seconds"] = round(time.time() - video_started, 2)
                    slide_state["musetalk"] = result.metadata.get("resident_runtime") if result.metadata else None
                else:
                    slide_state["video"] = "skipped"

                slide_state["compose"] = "running"
                emit(
                    22 + int((pos - 1) / total * 70),
                    f"slide_{slide.index}_compose",
                    stage=4,
                    stage_name="逐页画面排版",
                    current_slide=slide.index,
                    detail=f"正在合成第 {slide.index} 页画面",
                )
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
                    pip_position=str(override.get("pip_position") or settings_payload.get("pip_position") or "bottom_right"),
                    pip_size=str(override.get("pip_size") or settings_payload.get("pip_size") or "medium"),
                    custom_bg=override.get("custom_bg") or settings_payload.get("custom_bg"),
                    bg_blur=bool(override.get("bg_blur", settings_payload.get("bg_blur", False))),
                    pip_box=override.get("pip_box") or settings_payload.get("pip_box"),
                    ppt_box=override.get("ppt_box") or settings_payload.get("ppt_box"),
                )
                slide_state["compose"] = "done"
                clips.append(target)

                segment_subs = SubtitlesGenerator.generate_segment_subtitles(
                    text=plan["narration"],
                    duration=duration,
                    start_offset=cursor,
                    start_index=subtitle_index,
                )
                subtitle_items.extend(segment_subs)
                cursor += duration
                subtitle_index += len(segment_subs)
                audio_future = next_future

            emit(88, "concat", stage=4, stage_name="全片拼接与字幕", detail="正在拼接全部页面")
            raw_output = work / "course.mp4"
            self.composer.concat(clips, raw_output, work / "concat")
            srt = SubtitlesGenerator.build_srt_file(subtitle_items, work / "course.srt")
            SubtitlesGenerator.build_vtt_file(subtitle_items, work / "course.vtt")
            output = work / "result.mp4"

            # The studio's subtitle toggle historically wrote embed_subtitles.
            # Treat it as the user's intent to show subtitles, but use the mature
            # local hard-subtitle pipeline by default.  A soft track remains
            # available explicitly via subtitle_mode=soft.
            show_subtitles = bool(settings_payload.get("embed_subtitles", settings_payload.get("burn_subtitles", True)))
            subtitle_mode = str(settings_payload.get("subtitle_mode") or "burn").lower()
            if show_subtitles and subtitle_items:
                emit(93, "subtitles", stage=4, stage_name="全片拼接与字幕", detail="正在压制中文字幕")
                if subtitle_mode == "soft":
                    self.composer.embed_subtitles(raw_output, srt, output)
                else:
                    self.composer.burn_in_subtitles(
                        video_path=raw_output,
                        srt_path=srt,
                        output_path=output,
                        font_size=int(settings_payload.get("subtitle_font_size") or 34),
                        margin_bottom=int(settings_payload.get("subtitle_margin_bottom") or 42),
                    )
            else:
                output = raw_output
            emit(95, "postprocess", stage=4, stage_name="后处理", detail="课程主体生成完成，准备 AI 标识与上传")
            return output
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            if tts_runtime is not None:
                try:
                    tts_runtime.provider.release()
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


def _update_record(job_id: str, *, runtime_detail: dict[str, Any] | None = None, **values) -> None:
    with SessionLocal() as db:
        record = db.get(RenderJobRecord, job_id)
        if record is None:
            return
        for key, value in values.items():
            if hasattr(record, key):
                setattr(record, key, value)
        if runtime_detail is not None:
            try:
                payload = json.loads(record.payload_json or "{}")
            except Exception:
                payload = {}
            payload["_runtime"] = runtime_detail
            record.payload_json = json.dumps(payload, ensure_ascii=False)
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

    def progress(value: int, stage: str, detail: dict[str, Any] | None = None) -> None:
        if _record_is_canceled(job.id):
            raise RuntimeError("Render canceled")
        _update_record(
            job.id,
            progress=max(0, min(int(value), 99)),
            stage=stage,
            runtime_detail=detail,
        )
        job_queue.heartbeat(job.id)

    try:
        output = handler.render(job, progress=progress)
        if _record_is_canceled(job.id):
            raise RuntimeError("Render canceled")
        _update_record(job.id, progress=96, stage="ai_label")
        labeled_output = _apply_ai_label(output)
        duration = None
        try:
            duration = media_duration(labeled_output)
        except Exception:
            pass
        enforce_size = labeled_output.stat().st_size

        with SessionLocal() as db:
            enforce_storage_limit(db, job.tenant_id, incoming_bytes=enforce_size)

        _update_record(job.id, progress=98, stage="uploading")
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
                try:
                    payload = json.loads(record.payload_json or "{}")
                    runtime = payload.get("_runtime") or {}
                    runtime.update(
                        {
                            "stage": 5,
                            "stage_name": "完成",
                            "step_detail": "课程生成完成",
                            "elapsed_seconds": round(elapsed, 1),
                            "eta_seconds": 0,
                        }
                    )
                    payload["_runtime"] = runtime
                    record.payload_json = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    pass
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
                try:
                    payload = json.loads(record.payload_json or "{}")
                    runtime = payload.get("_runtime") or {}
                    runtime["step_detail"] = str(exc)
                    runtime["failed"] = True
                    payload["_runtime"] = runtime
                    record.payload_json = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    pass
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
