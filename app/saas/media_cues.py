from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..composer import ComposeConfig, ComposeError
from ..video_encoding import ffmpeg_video_encode_args


_ALLOWED_DISPLAY_MODES = {"fullscreen", "content_area", "overlay"}
_ALLOWED_AUDIO_MODES = {"mute", "duck", "original"}
_ALLOWED_TRANSITIONS = {"cut", "fade"}
_OVERLAY_POSITIONS = {
    "right_top",
    "left_top",
    "right_bottom",
    "left_bottom",
    "center",
}


@dataclass(frozen=True)
class ResolvedMediaCue:
    id: str
    asset_id: str
    media_type: str
    display_mode: str
    start_seconds: float
    end_seconds: float
    source_start_seconds: float
    source_end_seconds: float | None
    audio_mode: str
    audio_gain: float
    enter_transition: str
    exit_transition: str
    overlay_position: str
    alignment_quality: str = "estimated"

    @property
    def duration(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


def media_cue_asset_ids(raw_cues: Any) -> set[str]:
    if not isinstance(raw_cues, list):
        return set()
    return {
        str(cue.get("asset_id"))
        for cue in raw_cues
        if isinstance(cue, dict) and cue.get("asset_id")
    }


def _speech_weight_char(char: str) -> float:
    if not char:
        return 0.0
    if char.isspace():
        return 0.15
    if char in "，,、":
        return 0.28
    if char in "。！？!?；;：:":
        return 0.55
    if char in "（）()【】[]“”\"'《》<>":
        return 0.18
    if re.match(r"[\w\u3400-\u9fff]", char, re.UNICODE):
        return 1.0
    return 0.45


def _speech_weight(text: str) -> float:
    return max(0.0, sum(_speech_weight_char(char) for char in text))


def _anchor_offsets(narration: str, anchor: Mapping[str, Any]) -> tuple[int, int]:
    selected = str(anchor.get("selected_text") or "")
    if not selected:
        raise ValueError("内容镜头缺少绑定讲稿")

    try:
        start = int(anchor.get("start_offset"))
        end = int(anchor.get("end_offset"))
    except (TypeError, ValueError):
        start = -1
        end = -1

    if 0 <= start < end <= len(narration) and narration[start:end] == selected:
        return start, end

    hits: list[int] = []
    cursor = 0
    while True:
        found = narration.find(selected, cursor)
        if found < 0:
            break
        hits.append(found)
        cursor = found + max(1, len(selected))

    if len(hits) != 1:
        raise ValueError("内容镜头绑定讲稿已变化，请回到文稿确认页重新确认")
    return hits[0], hits[0] + len(selected)


def validate_media_cue_definitions(raw_cues: Any, *, narration: str) -> list[str]:
    """Validate text anchors and cue-local settings without touching storage."""

    if not isinstance(raw_cues, list) or not raw_cues:
        return []

    issues: list[str] = []
    ranges: list[tuple[int, int, str]] = []
    for position, raw in enumerate(raw_cues, start=1):
        if not isinstance(raw, dict):
            issues.append(f"内容镜头 {position} 数据无效")
            continue
        cue_id = str(raw.get("id") or f"#{position}")
        if str(raw.get("status") or "valid") != "valid":
            issues.append(f"内容镜头 {cue_id} 的绑定文字需要重新确认")
        if not raw.get("asset_id"):
            issues.append(f"内容镜头 {cue_id} 未选择素材")

        try:
            start, end = _anchor_offsets(
                narration,
                raw.get("anchor") if isinstance(raw.get("anchor"), dict) else {},
            )
        except ValueError as exc:
            issues.append(f"内容镜头 {cue_id}：{exc}")
        else:
            ranges.append((start, end, cue_id))

        try:
            source_start = max(0.0, float(raw.get("source_start_ms") or 0))
        except (TypeError, ValueError):
            source_start = 0.0
        if raw.get("source_end_ms") not in {None, ""}:
            try:
                source_end = float(raw.get("source_end_ms"))
            except (TypeError, ValueError):
                issues.append(f"内容镜头 {cue_id} 的素材终点无效")
            else:
                if source_end <= source_start:
                    issues.append(f"内容镜头 {cue_id} 的素材终点必须大于起点")

        media_type = str(raw.get("media_type") or "video").strip().lower()
        audio_mode = str(raw.get("audio_mode") or "mute").strip().lower()
        if media_type == "image" and audio_mode == "original":
            issues.append(f"内容镜头 {cue_id} 是图片，不能使用素材原声替代讲解")

    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] < previous[1]:
            issues.append(
                f"内容镜头 {previous[2]} 与 {current[2]} 的讲稿绑定范围重叠"
            )
    return issues


def resolve_media_cue_timeline(
    raw_cues: Any,
    *,
    narration: str,
    audio_duration: float,
) -> list[ResolvedMediaCue]:
    if not isinstance(raw_cues, list) or not raw_cues:
        return []
    if audio_duration <= 0:
        raise ValueError("内容镜头无法对齐：页面音频时长无效")

    total_weight = _speech_weight(narration)
    if total_weight <= 0:
        raise ValueError("内容镜头无法对齐：页面讲稿为空")

    resolved: list[ResolvedMediaCue] = []
    for raw in raw_cues:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("status") or "valid") != "valid":
            raise ValueError("存在待确认的内容镜头，请回到文稿确认页处理")

        cue_id = str(raw.get("id") or "")
        asset_id = str(raw.get("asset_id") or "")
        if not cue_id or not asset_id:
            raise ValueError("内容镜头缺少素材或镜头 ID")

        anchor = raw.get("anchor") if isinstance(raw.get("anchor"), dict) else {}
        start_offset, end_offset = _anchor_offsets(narration, anchor)
        before_weight = _speech_weight(narration[:start_offset])
        through_weight = _speech_weight(narration[:end_offset])
        start_seconds = max(0.0, min(audio_duration, audio_duration * before_weight / total_weight))
        end_seconds = max(start_seconds, min(audio_duration, audio_duration * through_weight / total_weight))

        # Extremely short selections create visually jarring single-frame cuts.
        # Preserve the text anchor while enforcing a small usable visual window.
        if end_seconds - start_seconds < 0.35:
            end_seconds = min(audio_duration, start_seconds + 0.35)
            if end_seconds - start_seconds < 0.20:
                start_seconds = max(0.0, end_seconds - 0.20)

        display_mode = str(raw.get("display_mode") or "content_area").strip().lower()
        if display_mode not in _ALLOWED_DISPLAY_MODES:
            display_mode = "content_area"

        media_type = str(raw.get("media_type") or "video").strip().lower()
        if media_type not in {"video", "image"}:
            media_type = "video"

        audio_mode = str(raw.get("audio_mode") or "mute").strip().lower()
        if audio_mode not in _ALLOWED_AUDIO_MODES:
            audio_mode = "mute"

        try:
            audio_gain = float(raw.get("audio_gain") if raw.get("audio_gain") is not None else 0.2)
        except (TypeError, ValueError):
            audio_gain = 0.2
        audio_gain = max(0.0, min(1.0, audio_gain))

        enter = str(raw.get("enter_transition") or "cut").strip().lower()
        exit_ = str(raw.get("exit_transition") or "cut").strip().lower()
        if enter not in _ALLOWED_TRANSITIONS:
            enter = "cut"
        if exit_ not in _ALLOWED_TRANSITIONS:
            exit_ = "cut"

        position = str(raw.get("overlay_position") or "right_top").strip().lower()
        if position not in _OVERLAY_POSITIONS:
            position = "right_top"

        try:
            source_start = max(0.0, float(raw.get("source_start_ms") or 0) / 1000.0)
        except (TypeError, ValueError):
            source_start = 0.0
        source_end: float | None = None
        if raw.get("source_end_ms") not in {None, ""}:
            try:
                source_end = max(0.0, float(raw.get("source_end_ms")) / 1000.0)
            except (TypeError, ValueError):
                source_end = None
            if source_end is not None and source_end <= source_start:
                raise ValueError(f"内容镜头 {cue_id} 的素材终点必须大于起点")

        resolved.append(
            ResolvedMediaCue(
                id=cue_id,
                asset_id=asset_id,
                media_type=media_type,
                display_mode=display_mode,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                source_start_seconds=source_start,
                source_end_seconds=source_end,
                audio_mode=audio_mode,
                audio_gain=audio_gain,
                enter_transition=enter,
                exit_transition=exit_,
                overlay_position=position,
            )
        )

    resolved.sort(key=lambda cue: (cue.start_seconds, cue.end_seconds, cue.id))
    previous: ResolvedMediaCue | None = None
    for cue in resolved:
        if previous is not None and cue.start_seconds < previous.end_seconds - 0.02:
            raise ValueError(
                f"内容镜头 {previous.id} 与 {cue.id} 的讲稿区间重叠，请调整绑定文字"
            )
        previous = cue
    return resolved


def _probe_has_audio(path: Path) -> bool:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    try:
        streams = json.loads(proc.stdout or "{}").get("streams") or []
    except Exception:
        return False
    return bool(streams)


def _box_from_fraction(
    box: Mapping[str, Any] | None,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if not isinstance(box, Mapping):
        return 0, 0, width, height
    try:
        x_value = float(box.get("x", 0.0))
        y_value = float(box.get("y", 0.0))
        w_value = float(box.get("w", 1.0))
        h_value = float(box.get("h", 1.0))
    except (TypeError, ValueError):
        return 0, 0, width, height
    x = int(x_value * width) if x_value <= 1.0 else int(x_value)
    y = int(y_value * height) if y_value <= 1.0 else int(y_value)
    w = int(w_value * width) if w_value <= 1.0 else int(w_value)
    h = int(h_value * height) if h_value <= 1.0 else int(h_value)
    w = max(2, min(width, w - (w % 2)))
    h = max(2, min(height, h - (h % 2)))
    x = max(0, min(width - w, x))
    y = max(0, min(height - h, y))
    return x, y, w, h


def _cue_box(
    cue: ResolvedMediaCue,
    *,
    ppt_box: Mapping[str, Any] | None,
    layout: str,
    config: ComposeConfig,
) -> tuple[int, int, int, int]:
    if cue.display_mode == "fullscreen":
        return 0, 0, config.width, config.height
    if cue.display_mode == "content_area":
        if layout == "split":
            # Mirrors CourseComposer's 7:3 split slide geometry.
            slide_w = min(config.width, 1288)
            slide_h = min(config.height, 728)
            return 48, max(0, (config.height - slide_h) // 2), slide_w, slide_h
        if layout in {"full_slide", "full_avatar"}:
            return 0, 0, config.width, config.height
        return _box_from_fraction(ppt_box, width=config.width, height=config.height)

    # Keep picture-in-picture intentionally simple in V1. The box preserves
    # the source aspect ratio internally via scale+pad.
    w = int(config.width * 0.34)
    h = int(config.height * 0.34)
    w -= w % 2
    h -= h % 2
    margin_x = 44
    margin_y = 44
    positions = {
        "left_top": (margin_x, margin_y),
        "right_top": (config.width - w - margin_x, margin_y),
        "left_bottom": (margin_x, config.height - h - margin_y),
        "right_bottom": (config.width - w - margin_x, config.height - h - margin_y),
        "center": ((config.width - w) // 2, (config.height - h) // 2),
    }
    x, y = positions.get(cue.overlay_position, positions["right_top"])
    return x, y, w, h


def apply_media_cues(
    *,
    base_video: Path,
    output_path: Path,
    raw_cues: Any,
    asset_paths: Mapping[str, Path],
    narration: str,
    audio_duration: float,
    ppt_box: Mapping[str, Any] | None,
    layout: str = "pip",
    config: ComposeConfig | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Overlay script-linked media on a fully composed page video.

    V1 intentionally runs after the ordinary page composer. This keeps old
    courses byte-for-byte on the existing path when no cues are present and
    makes the feature compatible with both the legacy local worker and leased
    remote page workers.
    """

    cues = resolve_media_cue_timeline(
        raw_cues,
        narration=narration,
        audio_duration=audio_duration,
    )
    if not cues:
        return base_video, []

    cfg = config or ComposeConfig()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = ["-i", str(base_video)]
    input_index_by_cue: dict[str, int] = {}
    cue_has_audio: dict[str, bool] = {}

    for cue in cues:
        source = asset_paths.get(cue.asset_id)
        if source is None or not source.exists():
            raise ValueError(f"内容镜头素材缺失: {cue.asset_id}")
        input_index = len(input_index_by_cue) + 1
        input_index_by_cue[cue.id] = input_index

        if cue.media_type == "image":
            inputs.extend(["-loop", "1", "-framerate", str(cfg.fps), "-i", str(source)])
            cue_has_audio[cue.id] = False
        else:
            if cue.source_start_seconds > 0:
                inputs.extend(["-ss", f"{cue.source_start_seconds:.3f}"])
            inputs.extend(["-i", str(source)])
            cue_has_audio[cue.id] = _probe_has_audio(source)

    filter_parts: list[str] = ["[0:v]setpts=PTS-STARTPTS[basev]"]
    last_video = "basev"
    audio_mix_labels: list[str] = []
    base_audio_filters = [f"aresample={cfg.audio_rate}", "asetpts=PTS-STARTPTS"]

    timeline_metadata: list[dict[str, Any]] = []
    for order, cue in enumerate(cues, start=1):
        idx = input_index_by_cue[cue.id]
        x, y, w, h = _cue_box(cue, ppt_box=ppt_box, layout=layout, config=cfg)
        clip_duration = cue.duration
        if clip_duration <= 0:
            continue
        source_window = clip_duration
        if cue.source_end_seconds is not None:
            source_window = min(
                clip_duration,
                max(0.01, cue.source_end_seconds - cue.source_start_seconds),
            )

        filters = [
            f"trim=duration={source_window:.3f}",
            "setpts=PTS-STARTPTS",
            f"scale={w}:{h}:force_original_aspect_ratio=decrease",
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
            f"fps={cfg.fps}",
            "format=rgba",
        ]
        # Extend a short video/image by holding the last frame until the text
        # anchor ends. This is less distracting than automatically looping B-roll.
        if source_window < clip_duration - 0.001 or cue.media_type == "video":
            filters.append(f"tpad=stop_mode=clone:stop_duration={clip_duration:.3f}")
        filters.append(f"trim=duration={clip_duration:.3f}")

        fade_duration = min(0.25, max(0.08, clip_duration / 4.0))
        if cue.enter_transition == "fade":
            filters.append(f"fade=t=in:st=0:d={fade_duration:.3f}:alpha=1")
        if cue.exit_transition == "fade":
            fade_start = max(0.0, clip_duration - fade_duration)
            filters.append(f"fade=t=out:st={fade_start:.3f}:d={fade_duration:.3f}:alpha=1")
        filters.append(f"setpts=PTS+{cue.start_seconds:.6f}/TB")

        cue_label = f"cuev{order}"
        filter_parts.append(f"[{idx}:v]{','.join(filters)}[{cue_label}]")
        next_video = f"v{order}"
        filter_parts.append(
            f"[{last_video}][{cue_label}]overlay=x={x}:y={y}:"
            f"enable='between(t,{cue.start_seconds:.6f},{cue.end_seconds:.6f})':"
            f"eof_action=pass:shortest=0[{next_video}]"
        )
        last_video = next_video

        if cue.audio_mode == "original":
            if cue.media_type != "video" or not cue_has_audio.get(cue.id):
                raise ValueError(f"内容镜头 {cue.id} 选择了素材原声，但素材没有可用音轨")
            base_audio_filters.append(
                f"volume=0:enable='between(t,{cue.start_seconds:.6f},{cue.end_seconds:.6f})'"
            )

        if cue.media_type == "video" and cue.audio_mode in {"duck", "original"} and cue_has_audio.get(cue.id):
            gain = 1.0 if cue.audio_mode == "original" else cue.audio_gain
            delay_ms = max(0, int(round(cue.start_seconds * 1000)))
            audio_label = f"cuea{order}"
            filter_parts.append(
                f"[{idx}:a]atrim=duration={source_window:.3f},asetpts=PTS-STARTPTS,"
                f"volume={gain:.4f},adelay={delay_ms}:all=1[{audio_label}]"
            )
            audio_mix_labels.append(audio_label)

        timeline_metadata.append(
            {
                "id": cue.id,
                "asset_id": cue.asset_id,
                "start_seconds": round(cue.start_seconds, 3),
                "end_seconds": round(cue.end_seconds, 3),
                "display_mode": cue.display_mode,
                "audio_mode": cue.audio_mode,
                "alignment_quality": cue.alignment_quality,
            }
        )

    filter_parts.append(f"[0:a]{','.join(base_audio_filters)}[basea]")
    if audio_mix_labels:
        inputs_count = 1 + len(audio_mix_labels)
        audio_inputs = "[basea]" + "".join(f"[{label}]" for label in audio_mix_labels)
        filter_parts.append(
            f"{audio_inputs}amix=inputs={inputs_count}:normalize=0:duration=first[aout]"
        )
    else:
        filter_parts.append("[basea]anull[aout]")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        f"[{last_video}]",
        "-map",
        "[aout]",
        *ffmpeg_video_encode_args(crf=cfg.crf, software_preset="veryfast"),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(cfg.audio_rate),
        "-t",
        f"{audio_duration:.3f}",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        raise ComposeError(proc.stderr.strip() or "内容镜头 FFmpeg 合成失败")
    return output_path, timeline_metadata
