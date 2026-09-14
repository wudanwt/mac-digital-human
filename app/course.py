from __future__ import annotations

import json
import math
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .composer import CourseComposer, media_duration
from .config import settings
from .engines import LongCatMLXEngine, MuseTalkMLXEngine
from .presets import get_avatar_profile, get_prompt_preset
from .tts import MLXAudioTTS, TTSConfig


class CourseBuildError(RuntimeError):
    pass


@dataclass
class SegmentReport:
    id: str
    role: str
    requested_engine: str
    resolved_engine: str
    script: str
    audio: str
    video: str
    audio_seconds: float
    elapsed_seconds: float
    fallback_reason: str | None = None


@dataclass
class CourseBuildResult:
    course_id: str
    title: str
    output: str
    workspace: str
    elapsed_seconds: float
    segments: list[SegmentReport]

    def to_dict(self) -> dict:
        return asdict(self)


def _slug(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", text.strip()).strip("-")
    return value[:48] or uuid.uuid4().hex[:8]


def _resolve_path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _frames_for_duration(seconds: float, fps: int, minimum: int = 61, maximum: int = 125) -> int:
    desired = max(minimum, math.ceil(seconds * fps))
    frames = 4 * math.ceil(max(1, desired - 1) / 4) + 1
    return min(frames, maximum)


class CoursePipeline:
    """Turn a course manifest into TTS -> avatar clips -> one final MP4.

    The pipeline intentionally stages TTS first, releases its model, and only
    then starts video generation. This avoids keeping a TTS model resident while
    LongCat consumes most of the unified memory on a 48 GB Mac.
    """

    def __init__(self) -> None:
        self.musetalk = MuseTalkMLXEngine()
        self.longcat = LongCatMLXEngine()
        self.composer = CourseComposer()

    def build(self, manifest_path: Path, output: Path | None = None) -> CourseBuildResult:
        manifest_path = manifest_path.resolve()
        if not manifest_path.exists():
            raise CourseBuildError(f"manifest not found: {manifest_path}")
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CourseBuildError(f"invalid course manifest: {manifest_path}") from exc

        base = manifest_path.parent
        title = str(manifest.get("title") or manifest_path.stem)
        course_id = str(manifest.get("id") or f"{_slug(title)}-{time.strftime('%Y%m%d-%H%M%S')}")
        work = settings.workspace_dir / "courses" / course_id
        audio_dir = work / "audio"
        clip_dir = work / "clips"
        audio_dir.mkdir(parents=True, exist_ok=True)
        clip_dir.mkdir(parents=True, exist_ok=True)

        profile = get_avatar_profile(manifest.get("profile"))
        if manifest.get("profile") and profile is None:
            raise CourseBuildError(f"avatar profile not found: {manifest['profile']}")

        assets = dict(manifest.get("assets") or {})
        if profile:
            assets.setdefault("reference_image", profile.get("image"))
            assets.setdefault("master_video", profile.get("master_video"))
        master_video = _resolve_path(base, assets.get("master_video"))
        reference_image = _resolve_path(base, assets.get("reference_image"))

        profile_tts = dict(profile.get("tts") or {}) if profile else {}
        manifest_tts = dict(manifest.get("tts") or {})
        tts_payload = {**profile_tts, **manifest_tts}
        defaults = TTSConfig()
        ref_audio_value = tts_payload.get("ref_audio")
        ref_audio = _resolve_path(base, ref_audio_value) if ref_audio_value else None
        tts_config = TTSConfig(
            model=str(tts_payload.get("model") or defaults.model),
            voice=str(tts_payload.get("voice") or defaults.voice),
            language=str(tts_payload.get("language") or defaults.language),
            instruct=str(tts_payload.get("instruct") or defaults.instruct),
            clone_model=str(tts_payload.get("clone_model") or defaults.clone_model),
            ref_audio=str(ref_audio) if ref_audio else None,
            ref_text=tts_payload.get("ref_text"),
        )
        tts = MLXAudioTTS(tts_config)

        raw_segments = manifest.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise CourseBuildError("manifest.segments must be a non-empty list")

        default_prompt_preset = (
            manifest.get("prompt_preset")
            or (profile.get("prompt_preset") if profile else None)
            or "energy_training_studio"
        )
        profile_prompt = str(profile.get("prompt") or "") if profile else ""

        started = time.time()
        prepared: list[dict[str, Any]] = []

        # Phase A: synthesize all narration while the TTS model is hot.
        for index, item in enumerate(raw_segments, start=1):
            if not isinstance(item, dict):
                raise CourseBuildError(f"segment {index} must be an object")
            segment_id = str(item.get("id") or f"seg-{index:03d}")
            script = str(item.get("script") or "").strip()
            if not script:
                raise CourseBuildError(f"segment {segment_id} has no script")
            audio = audio_dir / f"{index:03d}-{_slug(segment_id)}.wav"
            tts.synthesize(script, audio)
            duration = media_duration(audio)
            prepared.append(
                {
                    "index": index,
                    "id": segment_id,
                    "role": str(item.get("role") or "body"),
                    "requested_engine": str(item.get("engine") or "auto"),
                    "script": script,
                    "audio": audio,
                    "audio_seconds": duration,
                    "prompt": item.get("prompt") or profile_prompt,
                    "prompt_preset": item.get("prompt_preset") or default_prompt_preset,
                    "seed": int(item.get("seed", 42)),
                }
            )

        # Free MLX TTS weights before loading LongCat.
        tts.release()

        reports: list[SegmentReport] = []
        clips: list[Path] = []
        longcat_max_frames = int(manifest.get("longcat_max_frames", 125))
        longcat_fps = settings.longcat_fps
        longcat_max_seconds = longcat_max_frames / longcat_fps

        for segment in prepared:
            seg_started = time.time()
            requested = segment["requested_engine"]
            role = segment["role"]
            if requested not in {"auto", "musetalk", "longcat"}:
                raise CourseBuildError(f"segment {segment['id']}: unsupported engine {requested}")

            resolved = requested
            fallback_reason: str | None = None
            if requested == "auto":
                resolved = "longcat" if role in {"hero", "intro", "section"} else "musetalk"

            if resolved == "longcat" and segment["audio_seconds"] > longcat_max_seconds:
                if requested == "longcat":
                    raise CourseBuildError(
                        f"segment {segment['id']} audio is {segment['audio_seconds']:.1f}s; "
                        f"LongCat limit is about {longcat_max_seconds:.1f}s at {longcat_max_frames} frames"
                    )
                resolved = "musetalk"
                fallback_reason = (
                    f"LongCat clip would exceed {longcat_max_frames} frames; "
                    "auto-fell back to MuseTalk"
                )

            target = clip_dir / f"{segment['index']:03d}-{_slug(segment['id'])}.mp4"
            if resolved == "longcat":
                if reference_image is None or not reference_image.exists():
                    raise CourseBuildError("LongCat segment requires a profile image or assets.reference_image")
                preset = get_prompt_preset(segment["prompt_preset"])
                prompt = str(segment["prompt"] or (preset.prompt if preset else settings.longcat_default_prompt))
                frames = _frames_for_duration(
                    segment["audio_seconds"],
                    longcat_fps,
                    minimum=61,
                    maximum=longcat_max_frames,
                )
                result = self.longcat.render(
                    reference_image,
                    segment["audio"],
                    prompt=prompt,
                    variant=settings.default_longcat_variant,
                    height=preset.height if preset else settings.longcat_height,
                    width=preset.width if preset else settings.longcat_width,
                    num_frames=frames,
                    seed=segment["seed"],
                    output=target,
                )
            else:
                if master_video is None or not master_video.exists():
                    raise CourseBuildError("MuseTalk segment requires a profile master_video or assets.master_video")
                result = self.musetalk.render(
                    master_video,
                    segment["audio"],
                    variant=settings.default_musetalk_variant,
                    output=target,
                )

            clips.append(result.output)
            reports.append(
                SegmentReport(
                    id=segment["id"],
                    role=role,
                    requested_engine=requested,
                    resolved_engine=resolved,
                    script=segment["script"],
                    audio=str(segment["audio"]),
                    video=str(result.output),
                    audio_seconds=round(segment["audio_seconds"], 3),
                    elapsed_seconds=round(time.time() - seg_started, 3),
                    fallback_reason=fallback_reason,
                )
            )

        final = output or (settings.outputs_dir / "courses" / course_id / "course.mp4")
        self.composer.concat(clips, final, work / "compose")
        elapsed = time.time() - started
        result = CourseBuildResult(
            course_id=course_id,
            title=title,
            output=str(final),
            workspace=str(work),
            elapsed_seconds=round(elapsed, 3),
            segments=reports,
        )
        (work / "course-report.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result
