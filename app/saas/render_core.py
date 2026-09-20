from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..composer import media_duration
from ..ppt import PresentationParser, PPTRenderer
from ..subtitles import SubtitleItem, SubtitlesGenerator
from ..video_encoding import video_encoder_info
from .media_cues import apply_media_cues


@dataclass(frozen=True)
class RenderWorkspace:
    root: Path
    slide_dir: Path
    audio_dir: Path
    avatar_dir: Path
    segment_dir: Path

    @classmethod
    def create(cls, root: Path) -> "RenderWorkspace":
        workspace = cls(
            root=root,
            slide_dir=root / "slides",
            audio_dir=root / "audio",
            avatar_dir=root / "avatars",
            segment_dir=root / "segments",
        )
        for path in (workspace.slide_dir, workspace.audio_dir, workspace.avatar_dir, workspace.segment_dir):
            path.mkdir(parents=True, exist_ok=True)
        return workspace


@dataclass(frozen=True)
class PageRenderPlan:
    index: int
    title: str
    narration: str
    layout: str
    override: dict[str, Any]
    slide: Any


@dataclass(frozen=True)
class PreparedCourse:
    workspace: RenderWorkspace
    deck: Any
    plans: tuple[PageRenderPlan, ...]
    settings_payload: dict[str, Any]


@dataclass(frozen=True)
class PageRenderResult:
    index: int
    segment_path: Path
    audio_path: Path
    audio_seconds: float
    audio_source: str
    tts_elapsed_seconds: float
    render_seconds: float | None = None
    compose_seconds: float | None = None
    media_cue_seconds: float | None = None
    metadata: dict[str, Any] | None = None


PageStageCallback = Callable[[str, dict[str, Any]], None]
AudioFactory = Callable[[PageRenderPlan], Path]


def build_page_plans(deck, script_entries: list[dict[str, Any]], settings_payload: dict[str, Any]) -> list[PageRenderPlan]:
    """Build immutable per-page execution plans from a prepared deck and snapshot."""

    script_map = {
        int(item.get("index", idx + 1)): item
        for idx, item in enumerate(script_entries)
        if isinstance(item, dict)
    }
    plans: list[PageRenderPlan] = []
    for slide in deck.slides:
        override = dict(script_map.get(slide.index, {}))
        narration = str(
            override.get("narration")
            or override.get("script")
            or slide.narration
            or slide.title
            or f"第{slide.index}页"
        ).strip()
        layout = str(override.get("layout") or settings_payload.get("layout") or slide.layout or "pip")
        plans.append(
            PageRenderPlan(
                index=int(slide.index),
                title=str(slide.title or ""),
                narration=narration,
                layout=layout,
                override=override,
                slide=slide,
            )
        )
    return plans


def prepare_course(
    *,
    ppt_path: Path,
    workspace: RenderWorkspace,
    script_entries: list[dict[str, Any]],
    settings_payload: dict[str, Any],
) -> PreparedCourse:
    """Prepare only deterministic deck artifacts; no model inference happens here."""

    deck = PresentationParser.parse(ppt_path)
    PPTRenderer.render_deck(deck, workspace.slide_dir, require_authentic=True)
    plans = build_page_plans(deck, script_entries, settings_payload)
    return PreparedCourse(
        workspace=workspace,
        deck=deck,
        plans=tuple(plans),
        settings_payload=dict(settings_payload),
    )


def _slide_image(workspace: RenderWorkspace, slide_index: int) -> Path:
    target = workspace.slide_dir / f"slide-{slide_index}.png"
    if target.exists():
        return target
    alternatives = sorted(workspace.slide_dir.glob(f"*{slide_index}*.png"))
    if alternatives:
        return alternatives[0]
    raise RuntimeError(f"prepared slide image missing: {slide_index}")


def execute_page(
    *,
    plan: PageRenderPlan,
    workspace: RenderWorkspace,
    prepare_audio: AudioFactory,
    avatar_engine,
    composer,
    master_path: Path,
    master_cache_key: str,
    job_id: str,
    settings_payload: dict[str, Any],
    prepared_audio: Path | None = None,
    prepared_audio_source: str | None = None,
    media_cue_assets: Mapping[str, Path] | None = None,
    on_stage: PageStageCallback | None = None,
) -> PageRenderResult:
    """Execute one page: audio -> lip sync -> page composition.

    All inputs are local paths or immutable values.  This is the execution unit a
    remote worker will later lease from the center API without database access.
    """

    if on_stage:
        on_stage("audio_start", {"slide_index": plan.index, "text_length": len(plan.narration)})
    audio_started = time.time()
    audio_path = prepared_audio or prepare_audio(plan)
    duration = media_duration(audio_path)
    tts_elapsed = time.time() - audio_started
    audio_source = prepared_audio_source or str(plan.override.get("audio_source") or "provided")
    if on_stage:
        on_stage(
            "audio_done",
            {
                "slide_index": plan.index,
                "audio_seconds": duration,
                "tts_elapsed_seconds": tts_elapsed,
                "audio_source": audio_source,
            },
        )

    avatar_video: Path | None = None
    render_seconds: float | None = None
    metadata: dict[str, Any] = {}
    if plan.layout != "full_slide":
        if on_stage:
            on_stage("video_start", {"slide_index": plan.index, "audio_seconds": duration})
        video_started = time.time()
        result = avatar_engine.render(
            video=master_path,
            audio=audio_path,
            job_id=f"{job_id}-slide-{plan.index}",
            master_cache_key=master_cache_key,
        )
        avatar_video = Path(result.output)
        render_seconds = time.time() - video_started
        metadata = dict(result.metadata or {})
        if on_stage:
            on_stage(
                "video_done",
                {
                    "slide_index": plan.index,
                    "render_seconds": render_seconds,
                    "metadata": metadata,
                },
            )
    elif on_stage:
        on_stage("video_skipped", {"slide_index": plan.index})

    if on_stage:
        on_stage("compose_start", {"slide_index": plan.index})
    compose_started = time.time()
    override = plan.override
    target = workspace.segment_dir / f"{plan.index:03d}.mp4"
    composer.compose_segment_layout(
        avatar_video=avatar_video,
        audio=audio_path,
        slide_image=_slide_image(workspace, plan.index),
        layout=plan.layout,
        target=target,
        pip_position=str(override.get("pip_position") or settings_payload.get("pip_position") or "bottom_right"),
        pip_size=str(override.get("pip_size") or settings_payload.get("pip_size") or "medium"),
        custom_bg=override.get("custom_bg") or settings_payload.get("custom_bg"),
        bg_blur=bool(override.get("bg_blur", settings_payload.get("bg_blur", False))),
        pip_box=override.get("pip_box") or settings_payload.get("pip_box"),
        ppt_box=override.get("ppt_box") or settings_payload.get("ppt_box"),
    )
    compose_seconds = time.time() - compose_started
    compose_encoder = str(video_encoder_info().get("selected") or "")
    metadata["compose_seconds"] = round(compose_seconds, 4)
    metadata["compose_video_encoder"] = compose_encoder

    raw_cues = override.get("media_cues")
    media_cue_seconds: float | None = None
    if isinstance(raw_cues, list) and raw_cues:
        if on_stage:
            on_stage("media_cue_start", {"slide_index": plan.index, "cue_count": len(raw_cues)})
        media_cue_started = time.time()
        cue_target = workspace.segment_dir / f"{plan.index:03d}-media-cues.mp4"
        target, cue_timeline = apply_media_cues(
            base_video=target,
            output_path=cue_target,
            raw_cues=raw_cues,
            asset_paths=media_cue_assets or {},
            narration=plan.narration,
            audio_duration=float(duration),
            ppt_box=override.get("ppt_box") or settings_payload.get("ppt_box"),
            layout=plan.layout,
            config=getattr(composer, "config", None),
        )
        media_cue_seconds = time.time() - media_cue_started
        media_cue_encoder = str(video_encoder_info().get("selected") or "")
        metadata["media_cues"] = cue_timeline
        metadata["media_cue_seconds"] = round(media_cue_seconds, 4)
        metadata["media_cue_video_encoder"] = media_cue_encoder
        if on_stage:
            on_stage(
                "media_cue_done",
                {
                    "slide_index": plan.index,
                    "cue_count": len(cue_timeline),
                    "timeline": cue_timeline,
                    "segment_path": str(target),
                    "media_cue_seconds": round(media_cue_seconds, 4),
                    "video_encoder": media_cue_encoder,
                },
            )

    if on_stage:
        on_stage(
            "compose_done",
            {
                "slide_index": plan.index,
                "segment_path": str(target),
                "compose_seconds": round(compose_seconds, 4),
                "video_encoder": compose_encoder,
                "media_cue_seconds": round(media_cue_seconds, 4) if media_cue_seconds is not None else None,
            },
        )

    return PageRenderResult(
        index=plan.index,
        segment_path=target,
        audio_path=audio_path,
        audio_seconds=float(duration),
        audio_source=audio_source,
        tts_elapsed_seconds=float(tts_elapsed),
        render_seconds=float(render_seconds) if render_seconds is not None else None,
        compose_seconds=float(compose_seconds),
        media_cue_seconds=float(media_cue_seconds) if media_cue_seconds is not None else None,
        metadata=metadata,
    )


def finalize_course(
    *,
    prepared: PreparedCourse,
    results: list[PageRenderResult],
    composer,
    prevalidated_clips: bool = False,
    ai_badge_path: Path | None = None,
) -> Path:
    """Concatenate validated page segments and generate the final subtitle timeline."""

    by_index = {result.index: result for result in results}
    ordered: list[PageRenderResult] = []
    for plan in prepared.plans:
        result = by_index.get(plan.index)
        if result is None:
            raise RuntimeError(f"page result missing before finalize: {plan.index}")
        ordered.append(result)

    work = prepared.workspace.root
    raw_output = work / "course.mp4"
    composer.concat(
        [item.segment_path for item in ordered],
        raw_output,
        work / "concat",
        prevalidated=prevalidated_clips,
    )

    subtitle_items: list[SubtitleItem] = []
    cursor = 0.0
    subtitle_index = 1
    plan_by_index = {plan.index: plan for plan in prepared.plans}
    for result in ordered:
        plan = plan_by_index[result.index]
        segment_subs = SubtitlesGenerator.generate_segment_subtitles(
            text=plan.narration,
            duration=result.audio_seconds,
            start_offset=cursor,
            start_index=subtitle_index,
        )
        subtitle_items.extend(segment_subs)
        cursor += result.audio_seconds
        subtitle_index += len(segment_subs)

    srt = SubtitlesGenerator.build_srt_file(subtitle_items, work / "course.srt")
    SubtitlesGenerator.build_vtt_file(subtitle_items, work / "course.vtt")
    output = work / "result.mp4"
    settings_payload = prepared.settings_payload
    show_subtitles = bool(settings_payload.get("embed_subtitles", settings_payload.get("burn_subtitles", True)))
    subtitle_mode = str(settings_payload.get("subtitle_mode") or "burn").lower()
    if show_subtitles and subtitle_items:
        if subtitle_mode == "soft":
            composer.embed_subtitles(raw_output, srt, output)
            if ai_badge_path is not None:
                return composer.overlay_ai_badge(output, ai_badge_path, work / "result-labeled.mp4")
        else:
            composer.burn_in_subtitles(
                video_path=raw_output,
                srt_path=srt,
                output_path=output,
                font_size=int(settings_payload.get("subtitle_font_size") or 40),
                margin_bottom=int(settings_payload.get("subtitle_margin_bottom") or 42),
                ai_badge_path=ai_badge_path,
            )
        return output
    if ai_badge_path is not None:
        return composer.overlay_ai_badge(raw_output, ai_badge_path, work / "result-labeled.mp4")
    return raw_output
