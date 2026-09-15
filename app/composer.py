"""Course video composer with multi-layout templates, audio ducking, and subtitle embedding."""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import settings


class ComposeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComposeConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 25
    crf: int = 18
    audio_rate: int = 48000


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ComposeError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    try:
        payload = json.loads(proc.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ComposeError(f"unable to read duration: {path}") from exc


class CourseComposer:
    def __init__(self, config: ComposeConfig | None = None) -> None:
        self.config = config or ComposeConfig()

    @staticmethod
    def _run(cmd: list[str]) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise ComposeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{err}")

    def normalize(self, source: Path, target: Path) -> Path:
        """Normalize any video clip into standard 1080p, 25fps, 48kHz AAC."""
        if not source.exists():
            raise ComposeError(f"clip not found: {source}")
        cfg = self.config
        target.parent.mkdir(parents=True, exist_ok=True)
        vf = (
            f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
            f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={cfg.fps},format=yuv420p"
        )
        self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vf",
                vf,
                "-af",
                f"aresample={cfg.audio_rate}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                str(cfg.crf),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        return target

    def compose_segment_layout(
        self,
        avatar_video: Path | None,
        audio: Path,
        slide_image: Path | None,
        layout: str,
        target: Path,
        pip_position: str = "bottom_right",
        pip_size: str = "medium",
        custom_bg: Path | str | None = None,
        bg_blur: bool = False,
        pip_box: dict[str, float] | None = None,
        ppt_box: dict[str, float] | None = None,
    ) -> Path:
        """Compose a single course segment according to layout template."""
        cfg = self.config
        target.parent.mkdir(parents=True, exist_ok=True)
        duration = media_duration(audio)

        # Fallback to full_avatar if no slide image provided
        if not slide_image or not slide_image.exists():
            if layout in {"pip", "split", "full_slide"}:
                layout = "full_avatar"

        # Resolve custom_bg to an existing Path if provided
        resolved_bg_path: Path | None = None
        if custom_bg and isinstance(custom_bg, (str, Path)) and str(custom_bg) not in {"blur", "black"}:
            p = Path(custom_bg)
            if p.exists():
                resolved_bg_path = p
            else:
                candidate = settings.workspace_dir / "backgrounds" / str(custom_bg)
                if candidate.exists():
                    resolved_bg_path = candidate
        has_bg_file = resolved_bg_path is not None and resolved_bg_path.exists()

        # 1. Full Slide (Voice-over narration only)
        if layout == "full_slide" or not avatar_video or not avatar_video.exists():
            if has_bg_file:
                vf = (
                    f"[1:v]scale={cfg.width}:{cfg.height}[bg];"
                    f"[0:v]scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2,fps={cfg.fps},format=yuv420p"
                )
                self._run(
                    [
                        "ffmpeg", "-y", "-loop", "1", "-t", f"{duration:.3f}",
                        "-i", str(slide_image), "-loop", "1", "-t", f"{duration:.3f}",
                        "-i", str(resolved_bg_path), "-i", str(audio),
                        "-filter_complex", vf,
                        "-map", "2:a",
                        "-af", f"aresample={cfg.audio_rate}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        str(target),
                    ]
                )
            elif bg_blur or custom_bg == "blur":
                vf = (
                    f"[0:v]scale={cfg.width}:{cfg.height},gblur=sigma=35[bg];"
                    f"[0:v]scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2,fps={cfg.fps},format=yuv420p"
                )
                self._run(
                    [
                        "ffmpeg", "-y", "-loop", "1", "-t", f"{duration:.3f}",
                        "-i", str(slide_image), "-i", str(audio),
                        "-filter_complex", vf,
                        "-af", f"aresample={cfg.audio_rate}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        str(target),
                    ]
                )
            else:
                vf = (
                    f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
                    f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"fps={cfg.fps},format=yuv420p"
                )
                self._run(
                    [
                        "ffmpeg", "-y", "-loop", "1", "-t", f"{duration:.3f}",
                        "-i", str(slide_image), "-i", str(audio),
                        "-vf", vf,
                        "-af", f"aresample={cfg.audio_rate}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                        str(target),
                    ]
                )
            return target

        # 2. Full Avatar (Intro, Outro, or focus)
        if layout == "full_avatar":
            vf = (
                f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
                f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps={cfg.fps},format=yuv420p"
            )
            self._run(
                [
                    "ffmpeg", "-y",
                    "-i", str(avatar_video), "-i", str(audio),
                    "-vf", vf,
                    "-map", "0:v", "-map", "1:a",
                    "-af", f"aresample={cfg.audio_rate}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    str(target),
                ]
            )
            return target

        # 3. Picture-in-Picture (PiP) / Custom Drag Canvas Multi-Layer
        if layout == "pip":
            # 3.1 Digital Human Avatar Coordinates
            if pip_box and isinstance(pip_box, dict):
                bx = float(pip_box.get("x", 0.68))
                by = float(pip_box.get("y", 0.40))
                bw = float(pip_box.get("w", 0.28))
                bh = float(pip_box.get("h", 0.55))

                target_w = int(bw * cfg.width) if bw <= 1.0 else int(bw)
                target_h = int(bh * cfg.height) if bh <= 1.0 else int(bh)
                target_w = max(160, min(cfg.width, target_w - (target_w % 2)))
                target_h = max(180, min(cfg.height, target_h - (target_h % 2)))

                pos_x = int(bx * cfg.width) if bx <= 1.0 else int(bx)
                pos_y = int(by * cfg.height) if by <= 1.0 else int(by)
                pos_x = max(0, min(cfg.width - target_w, pos_x))
                pos_y = max(0, min(cfg.height - target_h, pos_y))

                aw, ah = target_w, target_h
                pw, ph = aw + 6, ah + 6
                overlay_coord = f"x={pos_x}:y={pos_y}"
            else:
                size_map = {
                    "small": (400, 480, 406, 486),
                    "medium": (500, 600, 508, 608),
                    "large": (640, 768, 648, 776),
                }
                aw, ah, pw, ph = size_map.get(pip_size, size_map["medium"])
                pos_map = {
                    "bottom_right": "x=W-w-44:y=H-h-44",
                    "bottom_left": "x=44:y=H-h-44",
                    "top_right": "x=W-w-44:y=44",
                    "top_left": "x=44:y=44",
                    "center_right": "x=W-w-44:y=(H-h)/2",
                    "center_left": "x=44:y=(H-h)/2",
                }
                overlay_coord = pos_map.get(pip_position, pos_map["bottom_right"])

            # 3.2 PPT Window Coordinates
            is_custom_ppt = False
            ppt_x, ppt_y, ppt_w, ppt_h = 0, 0, cfg.width, cfg.height
            if ppt_box and isinstance(ppt_box, dict):
                px_val = float(ppt_box.get("x", 0.0))
                py_val = float(ppt_box.get("y", 0.0))
                pw_val = float(ppt_box.get("w", 1.0))
                ph_val = float(ppt_box.get("h", 1.0))
                # If PPT is scaled down or moved away from fullscreen
                if pw_val < 0.98 or ph_val < 0.98 or px_val > 0.02 or py_val > 0.02:
                    is_custom_ppt = True
                    ppt_w = int(pw_val * cfg.width) if pw_val <= 1.0 else int(pw_val)
                    ppt_h = int(ph_val * cfg.height) if ph_val <= 1.0 else int(ph_val)
                    ppt_w = max(320, min(cfg.width, ppt_w - (ppt_w % 2)))
                    ppt_h = max(180, min(cfg.height, ppt_h - (ppt_h % 2)))
                    ppt_x = int(px_val * cfg.width) if px_val <= 1.0 else int(px_val)
                    ppt_y = int(py_val * cfg.height) if py_val <= 1.0 else int(py_val)
                    ppt_x = max(0, min(cfg.width - ppt_w, ppt_x))
                    ppt_y = max(0, min(cfg.height - ppt_h, ppt_y))

            # 3.3 Base Background Source Filter
            if has_bg_file:
                bg_filter = f"[3:v]scale={cfg.width}:{cfg.height}[bg];"
            elif bg_blur or custom_bg == "blur":
                bg_filter = f"[0:v]scale={cfg.width}:{cfg.height},gblur=sigma=35[bg];"
            else:
                bg_filter = f"color=c=0x0a0f1d:s={cfg.width}x{cfg.height}:d={duration:.3f},fps={cfg.fps}[bg];"

            # 3.4 PPT Window Filter (Authentic aspect ratio & perfect centering)
            if is_custom_ppt:
                ppt_filter = (
                    f"[0:v]scale={ppt_w}:{ppt_h}:force_original_aspect_ratio=decrease,"
                    f"pad={ppt_w}:{ppt_h}:(ow-iw)/2:(oh-ih)/2:color=black@0,fps={cfg.fps}[ppt_win];"
                    f"[bg][ppt_win]overlay=x={ppt_x}:y={ppt_y}[slide];"
                )
            else:
                ppt_filter = (
                    f"[0:v]scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease[slide_fg];"
                    f"[bg][slide_fg]overlay=x=(W-w)/2:y=(H-h)/2[slide];"
                )

            # 3.5 Avatar Window Filter (Keep original aspect ratio & perfect centering, no clipping)
            avatar_filter = (
                f"[1:v]scale={aw}:{ah}:force_original_aspect_ratio=decrease,"
                f"pad={aw}:{ah}:(ow-iw)/2:(oh-ih)/2:color=black@0,fps={cfg.fps}[avatar];"
                f"[slide][avatar]overlay={overlay_coord}[outv]"
            )

            filter_graph = bg_filter + ppt_filter + avatar_filter


            inputs = [
                "-loop", "1", "-t", f"{duration:.3f}", "-i", str(slide_image),
                "-i", str(avatar_video),
                "-i", str(audio),
            ]
            if has_bg_file:
                inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(resolved_bg_path)])

            self._run(
                [
                    "ffmpeg", "-y",
                    *inputs,
                    "-filter_complex", filter_graph,
                    "-map", "[outv]",
                    "-map", "2:a",
                    "-af", f"aresample={cfg.audio_rate}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    str(target),
                ]
            )
            return target

        # 4. Side-by-Side Split (7:3 ratio)
        if layout == "split":
            bg_color = "0x0a0f1d"
            filter_graph = (
                f"color=c={bg_color}:s={cfg.width}x{cfg.height}:d={duration:.3f},fps={cfg.fps}[bg];"
                f"[0:v]scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1288:728:4:4:color=0x334155,fps={cfg.fps}[slide];"
                f"[1:v]scale=520:960:force_original_aspect_ratio=increase,crop=520:960,"
                f"pad=528:968:4:4:color=0x334155,fps={cfg.fps}[avatar];"
                f"[bg][slide]overlay=x=48:y=(H-h)/2[tmp];"
                f"[tmp][avatar]overlay=x=W-w-48:y=(H-h)/2[outv]"
            )
            self._run(
                [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    f"{duration:.3f}",
                    "-i",
                    str(slide_image),
                    "-i",
                    str(avatar_video),
                    "-i",
                    str(audio),
                    "-filter_complex",
                    filter_graph,
                    "-map",
                    "[outv]",
                    "-map",
                    "2:a",
                    "-af",
                    f"aresample={cfg.audio_rate}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(cfg.crf),
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    str(target),
                ]
            )
            return target

        # Default fallback
        return self.normalize(avatar_video, target)

    def concat(self, clips: list[Path], output: Path, workdir: Path) -> Path:
        """Concatenate normalized video segments into a single file."""
        if not clips:
            raise ComposeError("no clips to compose")
        normalized_dir = workdir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized: list[Path] = []
        for index, clip in enumerate(clips, start=1):
            target = normalized_dir / f"{index:03d}.mp4"
            normalized.append(self.normalize(clip, target))

        concat_file = workdir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.resolve().as_posix()}'\n" for path in normalized),
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        return output

    def embed_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        """Embed an SRT subtitle track as standard MP4 mov_text stream."""
        if not srt_path.exists():
            return video_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(srt_path),
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "mov_text",
                "-metadata:s:s:0",
                "language=chi",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        return output_path

    def burn_in_subtitles(
        self,
        video_path: Path,
        srt_path: Path,
        output_path: Path,
        font_size: int = 34,
        margin_bottom: int = 40,
    ) -> Path:
        """Burn high-contrast subtitles directly into the video frames using PIL overlay."""
        if not srt_path.exists():
            return video_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        import re
        import shutil
        from PIL import Image, ImageDraw, ImageFont

        content = srt_path.read_text(encoding="utf-8").strip()
        if not content:
            return video_path

        def time_to_sec(t_str: str) -> float:
            parts = t_str.replace(",", ".").split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

        entries: list[tuple[float, float, str]] = []
        pattern = re.compile(
            r"(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n(.*?)(?=\n\n|\n*$)",
            re.DOTALL,
        )
        for m in pattern.finditer(content):
            start = time_to_sec(m.group(2))
            end = time_to_sec(m.group(3))
            txt = m.group(4).strip()
            if txt:
                entries.append((start, end, txt))

        if not entries:
            return video_path

        font_candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        font_file = None
        for fc in font_candidates:
            if Path(fc).exists():
                font_file = fc
                break

        cfg = self.config
        temp_dir = output_path.parent / f"sub_cards_{output_path.stem}_{int(time.time())}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        filter_complex_parts = []
        inputs = ["-i", str(video_path)]
        last_out = "0:v"

        try:
            for idx, (st, et, txt) in enumerate(entries):
                card_path = temp_dir / f"card_{idx:04d}.png"
                img = Image.new("RGBA", (cfg.width, cfg.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                fnt = ImageFont.truetype(font_file, font_size) if font_file else ImageFont.load_default()

                bbox = draw.textbbox((0, 0), txt, font=fnt)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

                pad_x, pad_y = 28, 14
                box_w = min(tw + pad_x * 2, cfg.width - 80)
                box_h = th + pad_y * 2
                box_x = (cfg.width - box_w) // 2
                box_y = cfg.height - box_h - margin_bottom

                draw.rounded_rectangle(
                    [box_x, box_y, box_x + box_w, box_y + box_h],
                    radius=12,
                    fill=(15, 23, 42, 210),  # Slate 900 82%
                    outline=(255, 255, 255, 45),
                    width=1,
                )
                draw.text((box_x + pad_x, box_y + pad_y), txt, font=fnt, fill=(255, 255, 255, 255))
                img.save(card_path)

                input_idx = idx + 1
                inputs.extend(["-i", str(card_path)])
                next_out = f"vsub{idx}" if idx < len(entries) - 1 else "vout"
                filter_complex_parts.append(
                    f"[{last_out}][{input_idx}:v]overlay=0:0:enable='between(t,{st:.3f},{et:.3f})'[{next_out}]"
                )
                last_out = next_out

            fc_str = ";".join(filter_complex_parts)
            self._run(
                [
                    "ffmpeg", "-y",
                    *inputs,
                    "-filter_complex", fc_str,
                    "-map", f"[{last_out}]",
                    "-map", "0:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf),
                    "-c:a", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return output_path

    def mix_background_music(
        self,
        video_path: Path,
        bgm_path: Path,
        output_path: Path,
        bgm_volume: float = 0.15,
        ducking: bool = True,
    ) -> Path:
        """Mix BGM into video with optional sidechain audio ducking."""
        if not bgm_path.exists():
            return video_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        video_len = media_duration(video_path)

        if ducking:
            filter_graph = (
                f"[1:a]volume={bgm_volume}[bgm_low];"
                f"[bgm_low][0:a]sidechaincompress=threshold=0.12:ratio=5:attack=40:release=350[ducked];"
                f"[0:a][ducked]amix=inputs=2:weights=1.0 1.0:dropout_transition=2[aout]"
            )
        else:
            filter_graph = (
                f"[1:a]volume={bgm_volume}[bgm_low];"
                f"[0:a][bgm_low]amix=inputs=2:weights=1.0 1.0[aout]"
            )

        self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-stream_loop",
                "-1",
                "-i",
                str(bgm_path),
                "-filter_complex",
                filter_graph,
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{video_len:.3f}",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        return output_path
