from __future__ import annotations

import io
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from ..config import settings


ProgressFn = Callable[[int, str], None]
log = logging.getLogger("digital-human.saas.avatar-matting-engine")


def is_green_screen(rgb) -> bool:
    import numpy as np

    height, width = rgb.shape[:2]
    border = max(1, min(height, width) // 16)
    samples = np.concatenate(
        [rgb[:border].reshape(-1, 3), rgb[:, :border].reshape(-1, 3), rgb[:, -border:].reshape(-1, 3)],
        axis=0,
    ).astype(np.int16)
    green = samples[:, 1]
    return bool(np.mean((green > 120) & (green - np.maximum(samples[:, 0], samples[:, 2]) > 65)) > 0.8)


def despill_green(rgb, alpha):
    import cv2
    import numpy as np

    output = rgb.copy()
    red = rgb[:, :, 0].astype(np.float32)
    green = rgb[:, :, 1].astype(np.float32)
    blue = rgb[:, :, 2].astype(np.float32)
    other = np.maximum(red, blue)
    excess = np.maximum(0.0, green - other - 4.0)
    edge = cv2.dilate((alpha < 250).astype(np.uint8), np.ones((5, 5), np.uint8))
    strong_spill = (green - other > 40.0) & (green > other * 1.35) & (green > 55.0)
    output[:, :, 1] = np.clip(green - excess * (edge | strong_spill), 0, 255).astype(np.uint8)
    return output


class _OnnxMattingSession:
    name = "onnx-cpu"

    def __init__(self, model: str) -> None:
        from rembg import new_session, remove

        self._remove = remove
        self._session = new_session(model, providers=["CPUExecutionProvider"])

    def predict(self, rgb):
        return self._remove(rgb, session=self._session, only_mask=True, post_process_mask=False)


class _MPSMattingSession:
    name = "pytorch-mps-fp16"

    def __init__(self, model_dir: Path, input_size: int) -> None:
        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

        if not torch.backends.mps.is_available():
            raise RuntimeError("PyTorch MPS is not available")
        if not (model_dir / "model.safetensors").is_file():
            raise RuntimeError(f"BiRefNet PyTorch weights not found: {model_dir}")

        torch.set_float32_matmul_precision("high")
        self._torch = torch
        self._device = torch.device("mps")
        self._dtype = torch.float16
        self._transform = transforms.Compose(
            [
                transforms.Resize((input_size, input_size)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        self._model = AutoModelForImageSegmentation.from_pretrained(
            str(model_dir),
            trust_remote_code=True,
            local_files_only=True,
        ).eval().to(self._device, dtype=self._dtype)

    def predict(self, rgb):
        import numpy as np

        tensor = self._transform(Image.fromarray(rgb)).unsqueeze(0).to(self._device, dtype=self._dtype)
        with self._torch.inference_mode():
            prediction = self._model(tensor)[-1].sigmoid()[0, 0].float().cpu().numpy()
        return np.clip(prediction * 255.0 + 0.5, 0, 255).astype(np.uint8)


class _SceneForegroundRecovery:
    """Recover a static desk or podium that portrait-only weights omit."""

    def __init__(self, rgb, portrait_mask, *, low: float = 18.0, high: float = 34.0) -> None:
        import cv2
        import numpy as np

        self.enabled = False
        self.recovered_ratio = 0.0
        self._background = None
        self._recovered_alpha = None
        self._low = float(low)
        self._high = max(self._low + 1.0, float(high))

        height, width = portrait_mask.shape[:2]
        if height < 64 or width < 64:
            return

        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        x = xx / max(1, width - 1)
        y = yy / max(1, height - 1)
        features = np.stack([np.ones_like(x), x, y, x * y, x * x, y * y], axis=2)
        border = (yy < height * 0.22) | (xx < width * 0.07) | (xx > width * 0.93)
        sample_mask = border & (portrait_mask < 16)
        sample_count = int(sample_mask.sum())
        if sample_count < 500:
            return

        stride = max(1, sample_count // 30000)
        sample_features = features[sample_mask][::stride]
        sample_colors = lab[sample_mask][::stride]
        inliers = np.ones(len(sample_features), dtype=bool)
        coefficients = None
        for _ in range(5):
            if int(inliers.sum()) < 100:
                return
            coefficients = np.linalg.lstsq(
                sample_features[inliers],
                sample_colors[inliers],
                rcond=None,
            )[0]
            residual = np.linalg.norm(sample_features @ coefficients - sample_colors, axis=1)
            cutoff = max(3.0, float(np.percentile(residual[inliers], 72)))
            inliers = residual <= cutoff
        if coefficients is None:
            return

        self._background = np.einsum("hwf,fc->hwc", features, coefficients)
        color_alpha = self._color_alpha(lab)
        hard = (color_alpha > 32).astype(np.uint8)
        hard = cv2.morphologyEx(hard, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        hard = cv2.morphologyEx(hard, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

        count, labels, stats, _ = cv2.connectedComponentsWithStats(hard, 8)
        anchor = cv2.dilate((portrait_mask > 32).astype(np.uint8), np.ones((31, 31), np.uint8))
        support = np.zeros_like(hard)
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            component = labels == label
            if area > height * width * 0.008 and np.any(anchor[component]):
                support[component] = 1

        added = (support > 0) & (portrait_mask < 32)
        added_ratio = float(added.mean())
        if 0.008 <= added_ratio <= 0.35:
            lower_fraction = float(added[int(height * 0.52):].sum() / max(1, added.sum()))
            if lower_fraction < 0.58:
                return
            recovered = color_alpha * support
        else:
            # A mostly correct portrait mask can still leave translucent holes in
            # the desk edge. Keep this small correction below the presenter only.
            lower = np.zeros_like(hard)
            lower[int(height * 0.68):] = 1
            soft_gap = (support > 0) & (lower > 0) & (color_alpha > 220) & (portrait_mask < 200)
            soft_ratio = float(soft_gap.mean())
            if not 0.0001 <= soft_ratio <= 0.02:
                return
            recovered = np.where((support > 0) & (lower > 0), color_alpha, 0)
            added_ratio = soft_ratio

        self._recovered_alpha = recovered.astype(np.uint8)
        self._background = None
        self.recovered_ratio = added_ratio
        self.enabled = True

    def _color_alpha(self, lab):
        import numpy as np

        distance = np.linalg.norm(lab - self._background, axis=2)
        return np.clip(
            (distance - self._low) / (self._high - self._low) * 255.0,
            0,
            255,
        ).astype(np.uint8)

    def apply(self, rgb, portrait_mask):
        import numpy as np

        del rgb
        if not self.enabled:
            return portrait_mask
        return np.maximum(portrait_mask, self._recovered_alpha)


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
    backend: str
    foreground_recovery: bool
    foreground_recovered_ratio: float
    green_screen: bool
    elapsed_seconds: float


class PortraitMattingEngine:
    """One-time portrait background removal for digital-human master videos.

    The expensive segmentation model runs only here. Course rendering later reuses
    the generated alpha video and never invokes rembg again.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = (model or os.getenv("AVATAR_MATTING_MODEL", "birefnet-portrait")).strip() or "birefnet-portrait"
        self.backend = (os.getenv("AVATAR_MATTING_BACKEND", "auto").strip().lower() or "auto")
        if self.backend not in {"auto", "mps", "onnx"}:
            raise ValueError("AVATAR_MATTING_BACKEND must be auto, mps, or onnx")
        self.torch_model_dir = Path(
            os.getenv(
                "AVATAR_MATTING_TORCH_MODEL_DIR",
                str(settings.workspace_dir / "saas-matting-models" / "pytorch" / "BiRefNet-portrait"),
            )
        ).expanduser()
        self.input_size = max(256, int(os.getenv("AVATAR_MATTING_INPUT_SIZE", "1024")))
        self.preserve_scene_foreground = os.getenv("AVATAR_MATTING_PRESERVE_FOREGROUND", "1").strip().lower() not in {
            "0", "false", "no", "off",
        }
        self.foreground_distance_low = float(os.getenv("AVATAR_MATTING_FOREGROUND_DISTANCE_LOW", "18"))
        self.foreground_distance_high = float(os.getenv("AVATAR_MATTING_FOREGROUND_DISTANCE_HIGH", "34"))
        self.target_fps = float(os.getenv("AVATAR_MATTING_FPS", str(settings.musetalk_target_fps)))
        self.temporal_smoothing = min(0.65, max(0.0, float(os.getenv("AVATAR_MATTING_TEMPORAL_SMOOTHING", "0.18"))))
        self.edge_blur = max(0.0, float(os.getenv("AVATAR_MATTING_EDGE_BLUR", "0.7")))

    @staticmethod
    def readiness() -> dict:
        requested = (os.getenv("AVATAR_MATTING_BACKEND", "auto").strip().lower() or "auto")
        model_dir = Path(
            os.getenv(
                "AVATAR_MATTING_TORCH_MODEL_DIR",
                str(settings.workspace_dir / "saas-matting-models" / "pytorch" / "BiRefNet-portrait"),
            )
        ).expanduser()
        result = {
            "ready": False,
            "requested_backend": requested,
            "selected_backend": None,
            "rembg": False,
            "mps": False,
            "mps_model": (model_dir / "model.safetensors").is_file(),
            "opencv": False,
            "ffmpeg": False,
        }
        try:
            import rembg  # noqa: F401

            result["rembg"] = True
        except Exception as exc:
            result["rembg_error"] = str(exc)
        try:
            import torch
            import torchvision  # noqa: F401
            import transformers  # noqa: F401

            result["mps"] = bool(torch.backends.mps.is_available())
        except Exception as exc:
            result["mps_error"] = str(exc)
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
        mps_ready = bool(result["mps"] and result["mps_model"])
        if requested == "mps":
            backend_ready = mps_ready
            result["selected_backend"] = "pytorch-mps-fp16" if mps_ready else None
        elif requested == "onnx":
            backend_ready = bool(result["rembg"])
            result["selected_backend"] = "onnx-cpu" if backend_ready else None
        else:
            backend_ready = bool(mps_ready or result["rembg"])
            result["selected_backend"] = "pytorch-mps-fp16" if mps_ready else "onnx-cpu" if result["rembg"] else None
        result["ready"] = bool(backend_ready and result["opencv"] and result["ffmpeg"])
        return result

    def _new_session(self):
        if self.backend in {"auto", "mps"}:
            try:
                return _MPSMattingSession(self.torch_model_dir, self.input_size)
            except Exception:
                if self.backend == "mps":
                    raise
                log.exception("MPS matting initialization failed; falling back to ONNX CPU")
        return _OnnxMattingSession(self.model)

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
        import numpy as np

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
        import numpy as np

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
        session = self._new_session()
        if progress:
            progress(9, f"抠像加速后端：{session.name}")
        alpha_proc = self._raw_encoder(alpha_video, width=width, height=height, fps=fps, pix_fmt="gray", kind="alpha")
        white_proc = self._raw_encoder(white_preview, width=width, height=height, fps=fps, pix_fmt="bgr24", kind="white")
        if alpha_proc.stdin is None or white_proc.stdin is None:
            cap.release()
            raise RuntimeError("failed to open ffmpeg matting pipes")

        previous: np.ndarray | None = None
        foreground_recovery: _SceneForegroundRecovery | None = None
        green_screen: bool | None = None
        frame_count = 0
        poster_written = False
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if green_screen is None:
                    green_screen = is_green_screen(rgb)
                raw_mask = session.predict(rgb)
                mask = self._decode_mask(raw_mask, width, height)
                if foreground_recovery is None and self.preserve_scene_foreground:
                    foreground_recovery = _SceneForegroundRecovery(
                        rgb,
                        mask,
                        low=self.foreground_distance_low,
                        high=self.foreground_distance_high,
                    )
                if foreground_recovery is not None:
                    mask = foreground_recovery.apply(rgb, mask)

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
                if green_screen:
                    frame = cv2.cvtColor(despill_green(rgb, mask), cv2.COLOR_RGB2BGR)
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
            backend=session.name,
            foreground_recovery=bool(foreground_recovery and foreground_recovery.enabled),
            foreground_recovered_ratio=foreground_recovery.recovered_ratio if foreground_recovery else 0.0,
            green_screen=bool(green_screen),
            elapsed_seconds=time.time() - started,
        )
