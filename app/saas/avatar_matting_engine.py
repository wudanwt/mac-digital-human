from __future__ import annotations

import io
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..config import settings


ProgressFn = Callable[[int, str], None]


@dataclass(frozen=True)
class MattingResult:
    alpha_video: Path
    poster_png: Path
    white_preview: Path
    frame_count: int
    fps: float
    width: int
    height: int
    model: str
    elapsed_seconds: float


class PortraitMattingEngine:
    """One-time portrait background removal for digital-human master videos.

    The expensive segmentation model runs only here. Course rendering later reuses
    the generated alpha video and never invokes rembg again.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = (model or os.getenv("AVATAR_MATTING_MODEL", "birefnet-portrait")).strip() or "birefnet-portrait"
        self.target_fps = float(os.getenv("AVATAR_MATTING_FPS", str(settings.musetalk_target_fps)))
        self.temporal_smoothing = min(0.65, max(0.0, float(os.getenv("AVATAR_MATTING_TEMPORAL_SMOOTHING", "0.18"))))
        self.edge_blur = max(0.0, float(os.getenv("AVATAR_MATTING_EDGE_BLUR", "0.7")))

    @staticmethod
    def readiness() -> dict:
        result = {"ready": False, "rembg": False, "opencv": False, "ffmpeg": False}
        try:
            import rembg  # noqa: F401

            result["rembg"] = True
        except Exception as exc:
            result["rembg_error"] = str(exc)
        try:
            import cv2  # noqa: F401

            result["opencv"] = True
        except Exception as exc:
            result["opencv_error"] = str(exc)
        try:
            proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            result["ffmpeg"] = proc.returncode == 0
        except Exception as exc:
            result["ffmpeg_error"] = str(exc)
        result["ready"] = bool(result["rembg"] and result["opencv"] and result["ffmpeg"])
        return result

    @staticmethod
    def _run(command: list[str]) -> None:
        proc = subprocess.run(command, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "ffmpeg command failed")

    def _normalize_master(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(source),
                "-vf", f"fps={self.target_fps:g}",
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-pix_fmt", "yuv420p",
                str(target),
            ]
        )

    @staticmethod
    def _decode_mask(value, width: int, height: int):
        import cv2

        if isinstance(value, (bytes, bytearray)):
            image = Image.open(io.BytesIO(value)).convert("L")
            mask = np.asarray(image, dtype=np.uint8)
        else:
            mask = np.asarray(value)
            if mask.ndim == 3:
                if mask.shape[2] == 4:
                    mask = mask[:, :, 3]
                else:
                    mask = cv2.cvtColor(mask.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            mask = mask.astype(np.uint8, copy=False)
        if mask.shape[:2] != (height, width):
            mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)
        return mask

    @staticmethod
    def _raw_encoder(path: Path, *, width: int, height: int, fps: float, pix_fmt: str, kind: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "pipe:0",
        ]
        if kind == "alpha":
            # A high-quality grayscale H.264 stream is browser-decodable and keeps
            # the 8-bit soft alpha edge while remaining much smaller than FFV1.
            command.extend(["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "8", "-pix_fmt", "yuv420p"])
        else:
            command.extend(["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"])
        command.extend(["-movflags", "+faststart", str(path)])
        return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def process(self, source: Path, workdir: Path, progress: ProgressFn | None = None) -> MattingResult:
        import cv2
        from rembg import new_session, remove

        if not source.exists():
            raise RuntimeError(f"master video not found: {source}")
        workdir.mkdir(parents=True, exist_ok=True)
        normalized = workdir / "master-25fps.mp4"
        alpha_video = workdir / "alpha-mask.mp4"
        poster_png = workdir / "transparent-poster.png"
        white_preview = workdir / "white-preview.mp4"
        started = time.time()

        if progress:
            progress(4, "正在标准化母版帧率")
        self._normalize_master(source, normalized)

        cap = cv2.VideoCapture(str(normalized))
        if not cap.isOpened():
            raise RuntimeError("cannot open normalized master video")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or self.target_fps)
        expected = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1))
        if width <= 0 or height <= 0:
            cap.release()
            raise RuntimeError("invalid master video dimensions")

        if progress:
            progress(8, f"正在加载 {self.model} 人像抠像模型")
        session = new_session(self.model)
        alpha_proc = self._raw_encoder(alpha_video, width=width, height=height, fps=fps, pix_fmt="gray", kind="alpha")
        white_proc = self._raw_encoder(white_preview, width=width, height=height, fps=fps, pix_fmt="bgr24", kind="white")
        if alpha_proc.stdin is None or white_proc.stdin is None:
            cap.release()
            raise RuntimeError("failed to open ffmpeg matting pipes")

        previous: np.ndarray | None = None
        frame_count = 0
        poster_written = False
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                raw_mask = remove(rgb, session=session, only_mask=True, post_process_mask=False)
                mask = self._decode_mask(raw_mask, width, height)

                if self.edge_blur > 0:
                    sigma = self.edge_blur
                    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
                if previous is not None and self.temporal_smoothing > 0:
                    mask = cv2.addWeighted(
                        mask,
                        1.0 - self.temporal_smoothing,
                        previous,
                        self.temporal_smoothing,
                        0,
                    )
                previous = mask.copy()

                alpha_proc.stdin.write(mask.tobytes())
                alpha_f = mask.astype(np.float32)[:, :, None] / 255.0
                white = np.clip(frame.astype(np.float32) * alpha_f + 255.0 * (1.0 - alpha_f), 0, 255).astype(np.uint8)
                white_proc.stdin.write(white.tobytes())

                if not poster_written:
                    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                    rgba[:, :, 3] = mask
                    Image.fromarray(rgba).save(poster_png)
                    poster_written = True

                frame_count += 1
                if progress and (frame_count == 1 or frame_count % 5 == 0):
                    pct = min(94, 10 + int(frame_count / max(1, expected) * 82))
                    progress(pct, f"正在抠像第 {frame_count}/{expected} 帧")
        finally:
            cap.release()
            try:
                alpha_proc.stdin.close()
            except Exception:
                pass
            try:
                white_proc.stdin.close()
            except Exception:
                pass

        alpha_err = alpha_proc.stderr.read().decode("utf-8", errors="replace") if alpha_proc.stderr else ""
        white_err = white_proc.stderr.read().decode("utf-8", errors="replace") if white_proc.stderr else ""
        alpha_code = alpha_proc.wait()
        white_code = white_proc.wait()
        if alpha_code != 0 or not alpha_video.exists():
            raise RuntimeError(alpha_err.strip() or f"alpha encoder failed ({alpha_code})")
        if white_code != 0 or not white_preview.exists():
            raise RuntimeError(white_err.strip() or f"white preview encoder failed ({white_code})")
        if frame_count <= 0 or not poster_png.exists():
            raise RuntimeError("matting produced no frames")

        if progress:
            progress(96, "透明资产编码完成")
        return MattingResult(
            alpha_video=alpha_video,
            poster_png=poster_png,
            white_preview=white_preview,
            frame_count=frame_count,
            fps=fps,
            width=width,
            height=height,
            model=self.model,
            elapsed_seconds=time.time() - started,
        )
