from __future__ import annotations

from pathlib import Path

from ..composer import ComposeError, CourseComposer, media_duration
from ..config import settings
from .avatar_matting_engine import is_green_screen


class TransparentCourseComposer(CourseComposer):
    """Course composer extension for pre-matted digital humans.

    ``transparent`` means the avatar's original background is removed and the
    lecturer is directly overlaid on the course canvas. ``white`` uses the same
    alpha but places a white panel behind the lecturer. No segmentation model is
    run here; this class only consumes the precomputed alpha video.
    """

    @staticmethod
    def _px(value: float, size: int) -> int:
        return int(value * size) if value <= 1.0 else int(value)

    @staticmethod
    def _box(box, default, width: int, height: int, *, min_w=160, min_h=180):
        data = box if isinstance(box, dict) else default
        x = TransparentCourseComposer._px(float(data.get("x", default["x"])), width)
        y = TransparentCourseComposer._px(float(data.get("y", default["y"])), height)
        w = TransparentCourseComposer._px(float(data.get("w", default["w"])), width)
        h = TransparentCourseComposer._px(float(data.get("h", default["h"])), height)
        w = max(min_w, min(width, w - (w % 2)))
        h = max(min_h, min(height, h - (h % 2)))
        x = max(0, min(width - w, x))
        y = max(0, min(height - h, y))
        return x, y, w, h

    @staticmethod
    def _needs_green_despill(video: Path) -> bool:
        import cv2

        cap = cv2.VideoCapture(str(video))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        return bool(ok and is_green_screen(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))

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
        *,
        avatar_alpha_video: Path | None = None,
        avatar_mode: str = "original",
    ) -> Path:
        mode = (avatar_mode or "original").strip().lower()
        if mode not in {"transparent", "white"} or layout == "full_slide" or not avatar_video:
            return super().compose_segment_layout(
                avatar_video=avatar_video,
                audio=audio,
                slide_image=slide_image,
                layout=layout,
                target=target,
                pip_position=pip_position,
                pip_size=pip_size,
                custom_bg=custom_bg,
                bg_blur=bg_blur,
                pip_box=pip_box,
                ppt_box=ppt_box,
            )
        if avatar_alpha_video is None or not avatar_alpha_video.exists():
            raise ComposeError(f"avatar mode {mode} requires a prepared alpha asset")
        if not avatar_video.exists():
            raise ComposeError(f"avatar video not found: {avatar_video}")
        rgb_filter = "format=rgb24"
        if self._needs_green_despill(avatar_video):
            rgb_filter += ",despill=type=green:mix=0.5:green=-1,format=rgb24"

        cfg = self.config
        duration = media_duration(audio)
        target.parent.mkdir(parents=True, exist_ok=True)

        resolved_bg: Path | None = None
        if custom_bg and str(custom_bg) not in {"blur", "black"}:
            candidate = Path(custom_bg)
            if candidate.exists():
                resolved_bg = candidate
            else:
                workspace_candidate = settings.workspace_dir / "backgrounds" / Path(str(custom_bg)).name
                if workspace_candidate.exists():
                    resolved_bg = workspace_candidate
        has_bg = bool(resolved_bg and resolved_bg.exists())

        if layout == "split":
            ppt_box = ppt_box or {"x": 0.025, "y": 0.06, "w": 0.64, "h": 0.88}
            pip_box = pip_box or {"x": 0.67, "y": 0.08, "w": 0.31, "h": 0.88}
            layout = "pip"

        if layout == "full_avatar":
            ax, ay, aw, ah = self._box(
                pip_box,
                {"x": 0.08, "y": 0.03, "w": 0.84, "h": 0.97},
                cfg.width,
                cfg.height,
                min_w=320,
                min_h=320,
            )
            inputs = ["-i", str(avatar_video), "-i", str(audio), "-i", str(avatar_alpha_video)]
            if has_bg:
                inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(resolved_bg)])
                bg = f"[3:v]scale={cfg.width}:{cfg.height},setsar=1[bg];"
            elif mode == "white":
                bg = f"color=c=white:s={cfg.width}x{cfg.height}:d={duration:.3f},fps={cfg.fps}[bg];"
            else:
                bg = f"color=c=0x0a0f1d:s={cfg.width}x{cfg.height}:d={duration:.3f},fps={cfg.fps}[bg];"
            graph = (
                bg
                + f"[0:v]fps={cfg.fps},{rgb_filter}[rgb];[2:v]fps={cfg.fps},format=gray[mask];"
                + "[rgb][mask]alphamerge,format=rgba[cut0];"
                + f"[cut0]scale={aw}:{ah}:force_original_aspect_ratio=decrease,format=rgba,"
                  f"pad={aw}:{ah}:(ow-iw)/2:oh-ih:color=0x00000000[cut];"
                + f"[bg][cut]overlay=x={ax}:y={ay}:format=auto[outv]"
            )
            self._run([
                "ffmpeg", "-y", *inputs, "-filter_complex", graph,
                "-map", "[outv]", "-map", "1:a",
                "-af", f"aresample={cfg.audio_rate}",
                "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(target),
            ])
            return target

        if layout != "pip":
            return super().compose_segment_layout(
                avatar_video=avatar_video,
                audio=audio,
                slide_image=slide_image,
                layout=layout,
                target=target,
                pip_position=pip_position,
                pip_size=pip_size,
                custom_bg=custom_bg,
                bg_blur=bg_blur,
                pip_box=pip_box,
                ppt_box=ppt_box,
            )
        if slide_image is None or not slide_image.exists():
            raise ComposeError("transparent PiP layout requires a slide image")

        px, py, pw, ph = self._box(
            ppt_box,
            {"x": 0.04, "y": 0.10, "w": 0.65, "h": 0.76},
            cfg.width,
            cfg.height,
            min_w=320,
            min_h=180,
        )
        ax, ay, aw, ah = self._box(
            pip_box,
            {"x": 0.71, "y": 0.25, "w": 0.25, "h": 0.70},
            cfg.width,
            cfg.height,
        )

        inputs = [
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(slide_image),
            "-i", str(avatar_video),
            "-i", str(audio),
            "-i", str(avatar_alpha_video),
        ]
        if has_bg:
            inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(resolved_bg)])
            bg_filter = f"[4:v]scale={cfg.width}:{cfg.height},setsar=1[bg];"
        elif bg_blur or custom_bg == "blur":
            bg_filter = f"[0:v]scale={cfg.width}:{cfg.height},gblur=sigma=35[bg];"
        else:
            bg_filter = f"color=c=0x0a0f1d:s={cfg.width}x{cfg.height}:d={duration:.3f},fps={cfg.fps}[bg];"

        ppt_filter = (
            f"[0:v]scale={pw}:{ph}:force_original_aspect_ratio=decrease,"
            f"pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2:color=black@0,fps={cfg.fps}[ppt];"
            f"[bg][ppt]overlay=x={px}:y={py}[slide];"
        )
        cut_filter = (
            f"[1:v]fps={cfg.fps},{rgb_filter}[rgb];[3:v]fps={cfg.fps},format=gray[mask];"
            "[rgb][mask]alphamerge,format=rgba[cut0];"
            f"[cut0]scale={aw}:{ah}:force_original_aspect_ratio=decrease,format=rgba,"
            f"pad={aw}:{ah}:(ow-iw)/2:oh-ih:color=0x00000000[cut];"
        )
        if mode == "white":
            avatar_filter = (
                f"color=c=white:s={aw}x{ah}:d={duration:.3f},fps={cfg.fps},format=rgba[whitepanel];"
                "[whitepanel][cut]overlay=0:0:format=auto[avatar_layer];"
            )
        else:
            avatar_filter = "[cut]null[avatar_layer];"
        graph = bg_filter + ppt_filter + cut_filter + avatar_filter + f"[slide][avatar_layer]overlay=x={ax}:y={ay}:format=auto[outv]"

        self._run([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", graph,
            "-map", "[outv]", "-map", "2:a",
            "-af", f"aresample={cfg.audio_rate}",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(target),
        ])
        return target
