"""End-to-end orchestration pipeline for PPT lecturing digital human micro-courses."""
from __future__ import annotations

import json
import math
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .composer import CourseComposer, media_duration
from .config import settings
from .engines import MuseTalkMLXEngine
from .ppt import CourseDeck, PresentationParser, PPTRenderer, SlideInfo
from .presets import get_avatar_profile, get_prompt_preset
from .subtitles import SubtitleItem, SubtitlesGenerator
from .tts import create_tts, infer_provider


class LectureBuildError(RuntimeError):
    pass


@dataclass
class SlideReport:
    index: int
    title: str
    layout: str
    script: str
    engine: str
    audio_path: str
    avatar_video_path: str | None
    composed_video_path: str
    duration_seconds: float
    elapsed_seconds: float
    fallback_reason: str | None = None


@dataclass
class LectureResult:
    lecture_id: str
    title: str
    output_video: str
    srt_path: str
    vtt_path: str
    workspace: str
    elapsed_seconds: float
    total_duration_seconds: float
    tts_provider: str
    slides: list[SlideReport]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LectureJob:
    id: str
    title: str
    status: str = "queued"  # queued, processing, completed, failed
    progress: int = 0
    message: str = "微课制作任务已进入队列"
    output_video: str | None = None
    srt_path: str | None = None
    vtt_path: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None

    # 4 阶段精细化进度与预测信息
    stage: int = 0  # 1: 课件解析, 2: 语音合成, 3: 数字人驱动, 4: 排版压制与字幕, 5: 完成
    stage_name: str = "等待中"
    current_step: int = 0
    total_steps: int = 0
    step_detail: str = "等待开始"
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    slide_progress: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LecturePipeline:
    """Orchestrates PPT parsing -> TTS -> avatar rendering -> layout composition -> subtitles & BGM."""

    def __init__(self) -> None:
        self.musetalk = MuseTalkMLXEngine()
        self.composer = CourseComposer()

    def build_from_ppt(
        self,
        ppt_path: str | Path,
        manifest_override: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> LectureResult:
        started_at = time.time()
        ppt = Path(ppt_path).resolve()
        if not ppt.exists():
            raise LectureBuildError(f"PPT file not found: {ppt}")

        override = manifest_override or {}
        deck: CourseDeck = PresentationParser.parse(ppt)

        # Allow manifest to override course title
        course_title = str(override.get("title") or deck.title)
        lecture_id = str(override.get("id") or f"lecture-{int(time.time())}-{uuid.uuid4().hex[:6]}")

        work = settings.workspace_dir / "lectures" / lecture_id
        slides_img_dir = work / "slides"
        audio_dir = work / "audio"
        avatar_dir = work / "avatars"
        segment_dir = work / "segments"

        for d in [slides_img_dir, audio_dir, avatar_dir, segment_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Apply slide overrides if user modified narration or layout
        slide_overrides: list[dict[str, Any]] = override.get("slides") or []
        override_map = {item.get("index"): item for item in slide_overrides if isinstance(item, dict)}
        for s in deck.slides:
            if s.index in override_map:
                o = override_map[s.index]
                if "narration" in o:
                    s.narration = str(o["narration"]).strip()
                if "layout" in o:
                    s.layout = str(o["layout"]).strip()
                if "title" in o:
                    s.title = str(o["title"]).strip()

        # Layout, styling and subtitle options
        pip_position = str(override.get("pip_position") or "bottom_right")
        pip_size = str(override.get("pip_size") or "medium")
        custom_bg = override.get("custom_bg")
        bg_blur = bool(override.get("bg_blur") or custom_bg == "blur")
        burn_subtitles = bool(override.get("burn_subtitles", True))

        total_slides_count = len(deck.slides)
        total_chars = sum(len((s.narration or s.title or f"第{s.index}页").strip()) for s in deck.slides)

        # 耗时预测估算模型（秒）
        # 1. PPT 解析与渲染底板: 约 2 ~ 4 秒
        est_stage1 = 3.0
        # 2. Audio8 ONNX 逐页合成: ~4.5 字/秒，加上频域降噪滤波
        est_stage2 = max(6.0, total_chars / 4.2)
        # 3. MuseTalk MLX 数字人渲染: 带面部关键点缓存约 0.85x 实时。音频预估时长约 total_chars / 4.0
        est_audio_dur = max(10.0, total_chars / 3.8)
        # 判断非 full_slide 页面
        avatar_slides = [s for s in deck.slides if s.layout != "full_slide"]
        est_stage3 = est_audio_dur * 0.9 if avatar_slides else 2.0
        # 4. 排版切片混剪与硬字幕烧录: 约每页 1.5 秒 + 最终合并与药丸字幕压制 5 秒
        est_stage4 = max(5.0, total_slides_count * 1.8 + 6.0)
        estimated_total_seconds = est_stage1 + est_stage2 + est_stage3 + est_stage4

        slide_prog_state = {
            "total_slides": total_slides_count,
            "audio": {s.index: "pending" for s in deck.slides},
            "video": {s.index: "pending" for s in deck.slides},
        }

        def report(
            stage: int,
            stage_name: str,
            progress: int,
            current_step: int,
            total_steps: int,
            step_detail: str,
            message: str | None = None,
        ):
            if not progress_callback:
                return
            now = time.time()
            elapsed = round(now - started_at, 1)
            # 计算平滑倒计时 ETA
            rem = estimated_total_seconds - elapsed
            if rem < 5.0:
                # 即使超时也给出一个平滑衰减的建议时间，不为负数
                rem = max(3.0, 15.0 / (1.0 + max(0.0, elapsed - estimated_total_seconds) * 0.15))
            eta = round(rem, 0)
            progress_callback(
                {
                    "stage": stage,
                    "stage_name": stage_name,
                    "progress": progress,
                    "current_step": current_step,
                    "total_steps": total_steps,
                    "step_detail": step_detail,
                    "message": message or step_detail,
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta,
                    "slide_progress": slide_prog_state,
                }
            )

        # ----------------------------------------------------------------------
        # 阶段 1：课件解析与底板渲染 (Stage 1)
        # ----------------------------------------------------------------------
        report(
            stage=1,
            stage_name="课件解析与底板生成",
            progress=5,
            current_step=1,
            total_steps=total_slides_count,
            step_detail=f"正在解析课件并渲染高清幻灯片底板 (共 {total_slides_count} 页)...",
        )
        PPTRenderer.render_deck(deck, slides_img_dir)
        report(
            stage=1,
            stage_name="课件解析与底板生成",
            progress=15,
            current_step=total_slides_count,
            total_steps=total_slides_count,
            step_detail="幻灯片高清底板渲染完成，准备人设资产与语音模型...",
        )

        # 加载人设模型及资产配置
        profile_name = override.get("profile") or override.get("profile_id") or "dan"
        profile = get_avatar_profile(profile_name)
        assets = dict(override.get("assets") or {})
        if profile:
            assets.setdefault("reference_image", profile.get("image"))
            assets.setdefault("master_video", profile.get("master_video"))

        base_dir = ppt.parent
        master_video_raw = assets.get("master_video")
        ref_image_raw = assets.get("reference_image")

        if master_video_raw:
            mv_path = Path(master_video_raw)
            master_video = mv_path if mv_path.is_absolute() else (base_dir / mv_path).resolve()
        else:
            master_video = None

        if ref_image_raw:
            ri_path = Path(ref_image_raw)
            ref_image = ri_path if ri_path.is_absolute() else (base_dir / ri_path).resolve()
        else:
            ref_image = None

        if master_video and not master_video.exists():
            candidate = settings.root / master_video_raw
            if candidate.exists():
                master_video = candidate

        if ref_image and not ref_image.exists():
            candidate = settings.root / ref_image_raw
            if candidate.exists():
                ref_image = candidate

        # TTS 情绪与速度配置
        speed = float(override.get("speed") or 1.0)
        speed = max(0.75, min(1.35, speed))
        emotion = str(override.get("emotion") or "professional").strip().lower()

        profile_tts = dict(profile.get("tts") or {}) if profile else {}
        manifest_tts = dict(override.get("tts") or {})
        tts_payload = {**profile_tts, **manifest_tts}

        if tts_payload.get("ref_audio") and tts_payload.get("voice") == "default":
            tts_payload["voice"] = profile_name

        tts_provider = infer_provider(tts_payload)
        tts_payload["speed"] = speed

        emotion_label = "标准专业"
        if emotion == "passionate":
            tts_payload.setdefault("temperature", 0.85)
            tts_payload.setdefault("top_p", 0.95)
            tts_payload.setdefault("instruct", "用激昂有力、富有感染力且充满热情的语气进行演讲授课<|endofprompt|>")
            tts_payload.setdefault("pause_seconds", 0.18)
            emotion_label = "激昂有力"
        elif emotion == "warm":
            tts_payload.setdefault("temperature", 0.75)
            tts_payload.setdefault("top_p", 0.92)
            tts_payload.setdefault("instruct", "用亲切温和、生动交流且通俗易懂的语气进行讲课<|endofprompt|>")
            tts_payload.setdefault("pause_seconds", 0.24)
            emotion_label = "亲切温和"
        elif emotion == "calm":
            tts_payload.setdefault("temperature", 0.6)
            tts_payload.setdefault("top_p", 0.85)
            tts_payload.setdefault("instruct", "用轻松自然、从容不迫、娓娓道来的语调进行讲解<|endofprompt|>")
            tts_payload.setdefault("pause_seconds", 0.28)
            emotion_label = "从容淡雅"
        else:
            tts_payload.setdefault("temperature", 0.65)
            tts_payload.setdefault("top_p", 0.88)
            tts_payload.setdefault("pause_seconds", 0.22)
            if tts_provider == "cosyvoice2":
                # 标准专业模式使用 100% 纯正 zero-shot 原声克隆，杜绝任何指令词外泄
                tts_payload.pop("instruct", None)
            else:
                tts_payload.setdefault("instruct", "用沉稳严谨、标准专业的大学讲师语气进行授课")

        tts = create_tts(tts_payload, base=base_dir)

        # ----------------------------------------------------------------------
        # 阶段 2：逐页高保真语音合成 (Stage 2)
        # ----------------------------------------------------------------------
        prepared_slides: list[dict[str, Any]] = []
        for idx, slide in enumerate(deck.slides, start=1):
            script = (slide.narration or slide.title or f"第 {slide.index} 页").strip()
            # 细粒度步骤播报：正在生成音频 idx/total
            pct = 15 + int(30 * ((idx - 1) / max(1, total_slides_count)))
            slide_prog_state["audio"][slide.index] = "synthesizing"
            report(
                stage=2,
                stage_name="逐页语音合成",
                progress=pct,
                current_step=idx,
                total_steps=total_slides_count,
                step_detail=f"正在生成音频 {idx}/{total_slides_count} (第{slide.index}页，字数: {len(script)}，语调: {emotion_label})...",
            )

            raw_audio_path = audio_dir / f"slide_{slide.index:03d}_raw.wav"
            final_audio_path = audio_dir / f"slide_{slide.index:03d}.wav"
            tts.synthesize(script, raw_audio_path)

            # 频域降噪滤波与语速处理适配
            if tts_provider == "cosyvoice2":
                # CosyVoice 2 原生高保真 24kHz 输出，已在模型流式 DiT 内按速度原生渲染；无需二次降噪或破坏性低通滤波
                af_filters = ["highpass=f=60", "volume=1.05"]
            else:
                af_filters = ["highpass=f=80", "lowpass=f=7500", "afftdn=nf=-25"]
                if abs(speed - 1.0) > 0.03:
                    af_filters.append(f"atempo={speed}")

            cmd = [
                "ffmpeg", "-y", "-i", str(raw_audio_path),
                "-af", ",".join(af_filters),
                "-ar", "16000", "-ac", "1",
                str(final_audio_path),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            raw_audio_path.unlink(missing_ok=True)

            duration = media_duration(final_audio_path)
            override_item = override_map.get(slide.index, {})
            slide_layout = str(override_item.get("layout") or slide.layout or "pip").strip()
            slide_pip_box = override_item.get("pip_box") or override.get("pip_box")
            slide_ppt_box = override_item.get("ppt_box") or override.get("ppt_box")
            slide_pip_pos = override_item.get("pip_position") or pip_position
            slide_pip_sz = override_item.get("pip_size") or pip_size
            slide_custom_bg = override_item.get("custom_bg") or custom_bg
            slide_bg_blur = bool(override_item.get("bg_blur", bg_blur))

            # 如果用户在排版阶段设置了画中画视窗、PPT视窗或背景底板，确保进入多图层合成
            if slide_ppt_box or slide_pip_box or slide_custom_bg:
                if slide_layout not in {"full_slide"}:
                    slide_layout = "pip"

            prepared_slides.append(
                {
                    "slide": slide,
                    "script": script,
                    "audio_path": final_audio_path,
                    "duration": duration,
                    "layout": slide_layout,
                    "pip_box": slide_pip_box,
                    "ppt_box": slide_ppt_box,
                    "pip_position": slide_pip_pos,
                    "pip_size": slide_pip_sz,
                    "custom_bg": slide_custom_bg,
                    "bg_blur": slide_bg_blur,
                }
            )
            slide_prog_state["audio"][slide.index] = "done"

        report(
            stage=2,
            stage_name="逐页语音合成",
            progress=45,
            current_step=total_slides_count,
            total_steps=total_slides_count,
            step_detail=f"全课件 {total_slides_count} 页语音合成完毕，准备渲染数字人视频...",
        )

        # ----------------------------------------------------------------------
        # 阶段 3：逐页数字人驱动与音唇同步 (Stage 3)
        # ----------------------------------------------------------------------
        segment_clips: list[Path] = []
        slide_reports: list[SlideReport] = []
        subtitle_items: list[SubtitleItem] = []
        time_cursor = 0.0
        sub_index = 1

        for idx, item in enumerate(prepared_slides, start=1):
            slide: SlideInfo = item["slide"]
            script: str = item["script"]
            audio_path: Path = item["audio_path"]
            duration: float = item["duration"]
            layout = item.get("layout") or slide.layout or "pip"

            step_started = time.time()
            avatar_video: Path | None = None
            resolved_engine = "none"
            fallback_reason: str | None = None

            pct = 45 + int(40 * ((idx - 1) / max(1, total_slides_count)))
            slide_prog_state["video"][slide.index] = "rendering"
            report(
                stage=3,
                stage_name="数字人视频渲染",
                progress=pct,
                current_step=idx,
                total_steps=total_slides_count,
                step_detail=f"正在生成数字人视频 {idx}/{total_slides_count} (第{slide.index}页，音频时长: {duration:.1f}s，人设: {profile_name})...",
            )

            if layout != "full_slide":
                avatar_video = avatar_dir / f"avatar_{slide.index:03d}.mp4"

                # 优先路线 1：使用母版视频 + MuseTalk MLX 毫秒级音唇同步
                if master_video and master_video.exists():
                    try:
                        resolved_engine = "musetalk"
                        self.musetalk.render(
                            video=master_video,
                            audio=audio_path,
                            output=avatar_video,
                        )
                    except Exception as exc:
                        fallback_reason = f"musetalk error: {exc}"
                        avatar_video = None

                # 优先路线 2：肖像图生成微动母版底板 + MuseTalk 极速驱动
                if not avatar_video and ref_image and ref_image.exists():
                    try:
                        resolved_engine = "musetalk_portrait"
                        anchor_mp4 = avatar_dir / f"anchor_{slide.index:03d}.mp4"
                        if not anchor_mp4.exists():
                            import cv2
                            import numpy as np
                            from PIL import Image

                            im = Image.open(ref_image).convert("RGB")
                            w, h = im.size
                            target_h = 1280
                            target_w = int(w * (target_h / h))
                            target_w = target_w - (target_w % 2)
                            im_resized = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            vw = cv2.VideoWriter(str(anchor_mp4), fourcc, 25, (target_w, target_h))
                            np_base = np.array(im_resized)
                            for _ in range(50):
                                vw.write(cv2.cvtColor(np_base, cv2.COLOR_RGB2BGR))
                            vw.release()

                        self.musetalk.render(
                            video=anchor_mp4,
                            audio=audio_path,
                            output=avatar_video,
                        )
                    except Exception as exc:
                        fallback_reason = f"musetalk portrait error: {exc}"
                        avatar_video = None

                # 兜底路线 3：静态肖像图
                if not avatar_video and ref_image and ref_image.exists():
                    resolved_engine = "portrait_image"
                    cmd = [
                        "ffmpeg", "-y", "-loop", "1", "-i", str(ref_image),
                        "-t", f"{duration:.3f}",
                        "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                        "-r", "25",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(avatar_video),
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                if not avatar_video:
                    fallback_reason = "no master video or portrait image; fallback to full_slide"
                    layout = "full_slide"
                    resolved_engine = "none"

            slide_prog_state["video"][slide.index] = "done"

            # 准备单页字幕与排版暂存
            seg_subs = SubtitlesGenerator.generate_segment_subtitles(
                text=script,
                duration=duration,
                start_offset=time_cursor,
                start_index=sub_index,
            )
            subtitle_items.extend(seg_subs)
            time_cursor += duration
            sub_index += len(seg_subs)

            # 保存切片信息
            item["avatar_video"] = avatar_video
            item["resolved_engine"] = resolved_engine
            item["fallback_reason"] = fallback_reason
            item["layout"] = layout

        # ----------------------------------------------------------------------
        # 阶段 4：排版混剪与内嵌字幕烧录 (Stage 4)
        # ----------------------------------------------------------------------
        report(
            stage=4,
            stage_name="排版混剪与字幕压制",
            progress=85,
            current_step=1,
            total_steps=total_slides_count,
            step_detail=f"正在排版混剪多轨画面 (位置: {pip_position}, 尺寸: {pip_size}, 毛玻璃背景: {'是' if bg_blur else '否'})...",
        )

        for idx, item in enumerate(prepared_slides, start=1):
            slide: SlideInfo = item["slide"]
            composed_clip = segment_dir / f"composed_{slide.index:03d}.mp4"
            step_started = time.time()

            self.composer.compose_segment_layout(
                avatar_video=item["avatar_video"],
                audio=item["audio_path"],
                slide_image=slide.image_path,
                layout=item["layout"],
                target=composed_clip,
                pip_position=item.get("pip_position") or pip_position,
                pip_size=item.get("pip_size") or pip_size,
                custom_bg=item.get("custom_bg") or custom_bg,
                bg_blur=item.get("bg_blur", bg_blur),
                pip_box=item.get("pip_box"),
                ppt_box=item.get("ppt_box"),
            )
            segment_clips.append(composed_clip)

            slide_reports.append(
                SlideReport(
                    index=slide.index,
                    title=slide.title,
                    layout=item["layout"],
                    script=item["script"],
                    engine=item["resolved_engine"],
                    audio_path=str(item["audio_path"]),
                    avatar_video_path=str(item["avatar_video"]) if item["avatar_video"] else None,
                    composed_video_path=str(composed_clip),
                    duration_seconds=round(item["duration"], 2),
                    elapsed_seconds=round(time.time() - step_started, 2),
                    fallback_reason=item["fallback_reason"],
                )
            )

        # 拼接全片
        out_base = output_dir or (settings.outputs_dir / "lectures" / lecture_id)
        out_base.mkdir(parents=True, exist_ok=True)
        raw_concat = work / "raw_course.mp4"
        self.composer.concat(segment_clips, raw_concat, workdir=work / "compose")

        # 生成外挂字幕文件 (.srt / .vtt)
        srt_file = out_base / "course.srt"
        vtt_file = out_base / "course.vtt"
        SubtitlesGenerator.build_srt_file(subtitle_items, srt_file)
        SubtitlesGenerator.build_vtt_file(subtitle_items, vtt_file)

        # 高清内嵌字幕烧录 (Burn-in Subtitles)
        subtitled_video = work / "subtitled_course.mp4"
        if burn_subtitles and srt_file.exists() and len(subtitle_items) > 0:
            report(
                stage=4,
                stage_name="排版混剪与字幕压制",
                progress=94,
                current_step=total_slides_count,
                total_steps=total_slides_count,
                step_detail="正在进行高对比度药丸背景中文字幕画面内嵌 (Burn-in Hard Subtitles)...",
            )
            self.composer.burn_in_subtitles(
                video_path=raw_concat,
                srt_path=srt_file,
                output_path=subtitled_video,
                font_size=34,
                margin_bottom=42,
            )
        else:
            self.composer.embed_subtitles(raw_concat, srt_file, subtitled_video)

        # 可选 BGM 混合与语音闪避
        bgm_path_raw = override.get("bgm")
        final_video = out_base / "course.mp4"
        if bgm_path_raw:
            bgm_path = Path(bgm_path_raw).resolve()
            if not bgm_path.exists():
                candidate = settings.root / bgm_path_raw
                if candidate.exists():
                    bgm_path = candidate
            if bgm_path.exists():
                report(
                    stage=4,
                    stage_name="排版混剪与字幕压制",
                    progress=97,
                    current_step=total_slides_count,
                    total_steps=total_slides_count,
                    step_detail="正在混合背景音乐并注入语音动态闪避音效...",
                )
                bgm_vol = float(override.get("bgm_volume", 0.12))
                self.composer.mix_background_music(
                    video_path=subtitled_video,
                    bgm_path=bgm_path,
                    output_path=final_video,
                    bgm_volume=bgm_vol,
                    ducking=True,
                )
            else:
                final_video = self.composer.normalize(subtitled_video, final_video)
        else:
            final_video = self.composer.normalize(subtitled_video, final_video)

        total_elapsed = time.time() - started_at
        result = LectureResult(
            lecture_id=lecture_id,
            title=course_title,
            output_video=str(final_video),
            srt_path=str(srt_file),
            vtt_path=str(vtt_file),
            workspace=str(work),
            elapsed_seconds=round(total_elapsed, 2),
            total_duration_seconds=round(time_cursor, 2),
            tts_provider=tts_provider,
            slides=slide_reports,
        )

        (work / "lecture-report.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ----------------------------------------------------------------------
        # 阶段 5：完成 (Stage 5)
        # ----------------------------------------------------------------------
        report(
            stage=5,
            stage_name="微课制作完成",
            progress=100,
            current_step=total_slides_count,
            total_steps=total_slides_count,
            step_detail=f"微课视频制作全部完成！全片时长 {time_cursor:.1f} 秒，总耗时 {total_elapsed:.1f} 秒",
            message="微课制作完成！",
        )

        return result


class LectureJobManager:
    """Manages asynchronous background lecture generation jobs with fine-grained real-time feedback."""

    def __init__(self) -> None:
        import threading
        self._jobs: dict[str, LectureJob] = {}
        self._lock = threading.Lock()
        self._pipeline = LecturePipeline()

    def get(self, job_id: str) -> LectureJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[LectureJob]:
        with self._lock:
            return list(self._jobs.values())

    def create_job(
        self,
        ppt_path: Path,
        manifest_override: dict[str, Any] | None = None,
        output_dir: Path | None = None,
    ) -> LectureJob:
        import threading
        override = manifest_override or {}
        job_id = str(override.get("id") or f"lec-{int(time.time())}-{uuid.uuid4().hex[:6]}")
        title = str(override.get("title") or ppt_path.stem)
        job = LectureJob(id=job_id, title=title)
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job, ppt_path, override, output_dir),
            daemon=True,
            name=f"lecture-worker-{job_id}",
        )
        thread.start()
        return job

    def _run_job(
        self,
        job: LectureJob,
        ppt_path: Path,
        override: dict[str, Any],
        output_dir: Path | None,
    ) -> None:
        import traceback

        def on_progress(p: dict[str, Any]) -> None:
            with self._lock:
                job.stage = p.get("stage", job.stage)
                job.stage_name = p.get("stage_name", job.stage_name)
                job.progress = p.get("progress", job.progress)
                job.current_step = p.get("current_step", job.current_step)
                job.total_steps = p.get("total_steps", job.total_steps)
                job.step_detail = p.get("step_detail", job.step_detail)
                job.message = p.get("message", job.message)
                job.elapsed_seconds = p.get("elapsed_seconds", job.elapsed_seconds)
                job.eta_seconds = p.get("eta_seconds", job.eta_seconds)
                if "slide_progress" in p:
                    job.slide_progress = p["slide_progress"]

        with self._lock:
            job.status = "processing"
            job.progress = 5
            job.stage = 1
            job.stage_name = "准备中"
            job.message = "正在初始化课件制作环境..."

        try:
            result = self._pipeline.build_from_ppt(
                ppt_path=ppt_path,
                manifest_override=override,
                output_dir=output_dir,
                progress_callback=on_progress,
            )
            with self._lock:
                job.progress = 100
                job.status = "completed"
                job.stage = 5
                job.stage_name = "微课制作完成"
                job.message = "微课制作完成！"
                job.output_video = result.output_video
                job.srt_path = result.srt_path
                job.vtt_path = result.vtt_path
                job.result = result.to_dict()
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = f"{exc}\n{traceback.format_exc()}"
                job.message = f"制作失败: {exc}"


lecture_job_manager = LectureJobManager()
