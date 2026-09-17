from __future__ import annotations

import functools
import json
import os
import pickle
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import settings

from .base import EngineError


@dataclass
class MasterMaterial:
    frame_paths: list[str]
    boxes: list[tuple[int, int, int, int] | None]
    crop_boxes: list[tuple[int, int, int, int] | None]
    masks: list[np.ndarray | None]
    latents: np.ndarray
    fps: float


class ResidentMuseTalkRuntime:
    """Long-lived MuseTalk MLX runtime for Apple Silicon course workers.

    The upstream helper script is intentionally simple, but starting it once per
    slide reloads MLX/FaceParsing and recomputes the same master-video VAE
    latents and blend masks.  This adapter keeps model objects resident and
    persists reusable master-video materials under ``workspace/cache/musetalk``.
    """

    PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)

    def __init__(self, variant: str) -> None:
        self.variant = variant
        self.mlx_root = settings.musetalk_mlx_dir.resolve()
        self.upstream = settings.musetalk_upstream_dir.resolve()
        self._materials: dict[str, MasterMaterial] = {}
        self.last_material_cache_status = "unprepared"
        self._batch_size: int | None = None
        self._load_runtime()

    def _load_runtime(self) -> None:
        if str(self.mlx_root) not in sys.path:
            sys.path.insert(0, str(self.mlx_root))
        if str(self.upstream) not in sys.path:
            sys.path.insert(0, str(self.upstream))
        utils = self.upstream / "musetalk" / "utils"
        if str(utils) not in sys.path:
            sys.path.insert(0, str(utils))

        try:
            import cv2
            import mlx.core as mx
            import torch
            from musetalk_mlx.pipeline_mlx import MuseTalkPipeline
            from musetalk.utils.blending import face_seg, get_crop_box, get_image_blending
            from musetalk.utils.face_parsing import FaceParsing
        except Exception as exc:  # pragma: no cover - only exercised on MLX hosts
            raise EngineError(f"MuseTalk resident runtime import failed: {exc}") from exc

        # MuseTalk's legacy BiSeNet checkpoint needs weights_only=False on newer torch.
        if not getattr(torch.load, "_mac_dh_compat", False):
            original = torch.load

            @functools.wraps(original)
            def compat_load(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return original(*args, **kwargs)

            compat_load._mac_dh_compat = True  # type: ignore[attr-defined]
            torch.load = compat_load

        self.cv2 = cv2
        self.mx = mx
        self.face_seg = face_seg
        self.get_crop_box = get_crop_box
        self.get_image_blending = get_image_blending
        mx.set_default_device(mx.gpu)

        model_dir = self.mlx_root / "dist" / f"MuseTalk-1.5-MLX-{self.variant}"
        started = time.time()
        self.pipe = MuseTalkPipeline.from_pretrained_mlx(model_dir)

        old_cwd = Path.cwd()
        try:
            os.chdir(self.upstream)
            self.face_parser = FaceParsing()
        finally:
            os.chdir(old_cwd)
        self.model_load_seconds = time.time() - started

    @staticmethod
    def _cycle_index(length: int, index: int) -> int:
        if length <= 1:
            return 0
        cycle = length * 2
        pos = index % cycle
        return pos if pos < length else cycle - pos - 1

    def _exact_blend_mask(
        self,
        frame: np.ndarray,
        box: tuple[int, int, int, int],
        *,
        mode: str,
        expand: float = 1.5,
        upper_boundary_ratio: float = 0.5,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Precompute the same mask used by upstream get_image(), once per frame."""
        from PIL import Image

        x, y, x1, y1 = box
        body = Image.fromarray(frame[:, :, ::-1])
        crop_box, _ = self.get_crop_box(box, expand)
        x_s, y_s, _, _ = crop_box
        face_large = body.crop(crop_box)
        mask_image = self.face_seg(face_large, mode=mode, fp=self.face_parser)
        if mask_image is None:
            raise EngineError("FaceParsing returned no blend mask")
        mask_image = mask_image.resize(face_large.size)
        mask_small = mask_image.crop((x - x_s, y - y_s, x1 - x_s, y1 - y_s))
        canvas = Image.new("L", face_large.size, 0)
        canvas.paste(mask_small, (x - x_s, y - y_s, x1 - x_s, y1 - y_s))
        width, height = canvas.size
        top = int(height * upper_boundary_ratio)
        lower = Image.new("L", canvas.size, 0)
        lower.paste(canvas.crop((0, top, width, height)), (0, top))
        kernel = int(0.05 * width // 2 * 2) + 1
        mask = self.cv2.GaussianBlur(np.array(lower), (max(1, kernel), max(1, kernel)), 0)
        return mask, tuple(int(v) for v in crop_box)

    def _material_key(self, coords_file: Path, extra_margin: int, parsing_mode: str) -> str:
        stat = coords_file.stat()
        return f"{coords_file.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{self.variant}:{extra_margin}:{parsing_mode}"

    def prepare_master(
        self,
        coords_file: Path,
        cache_dir: Path,
        *,
        extra_margin: int = 10,
        parsing_mode: str = "jaw",
    ) -> MasterMaterial:
        key = self._material_key(coords_file, extra_margin, parsing_mode)
        if key in self._materials:
            self.last_material_cache_status = "memory"
            return self._materials[key]

        material_dir = cache_dir / f"resident-{self.variant}-m{extra_margin}-{parsing_mode}"
        material_dir.mkdir(parents=True, exist_ok=True)
        latent_file = material_dir / "latents-f16.npy"
        blend_file = material_dir / "blend-material.pkl"
        manifest_file = material_dir / "manifest.json"

        with coords_file.open("rb") as fh:
            meta = pickle.load(fh)
        raw_coords = list(meta.get("coords", []))
        frame_paths = [str(Path(p).resolve()) for p in meta.get("frames", [])]
        fps = float(meta.get("fps") or settings.musetalk_target_fps)
        if not raw_coords or len(raw_coords) != len(frame_paths):
            raise EngineError("MuseTalk coords/frame cache is incomplete")

        expected = {
            "source": key,
            "frames": len(frame_paths),
            "variant": self.variant,
            "extra_margin": extra_margin,
            "parsing_mode": parsing_mode,
        }
        cached_ok = False
        if latent_file.exists() and blend_file.exists() and manifest_file.exists():
            try:
                cached_ok = json.loads(manifest_file.read_text(encoding="utf-8")) == expected
            except Exception:
                cached_ok = False

        if cached_ok:
            try:
                latents = np.load(latent_file, allow_pickle=False)
                with blend_file.open("rb") as fh:
                    blend = pickle.load(fh)
                if (latents.ndim < 2 or latents.shape[0] != len(frame_paths)
                        or latents.dtype != np.float16
                        or any(len(blend[name]) != len(frame_paths) for name in ("boxes", "crop_boxes", "masks"))):
                    raise ValueError("Incomplete MuseTalk resident material cache")
                material = MasterMaterial(
                    frame_paths=frame_paths,
                    boxes=blend["boxes"],
                    crop_boxes=blend["crop_boxes"],
                    masks=blend["masks"],
                    latents=latents,
                    fps=fps,
                )
                self._materials[key] = material
                self.last_material_cache_status = "disk"
                return material
            except (OSError, ValueError, KeyError, TypeError, pickle.PickleError):
                pass

        boxes: list[tuple[int, int, int, int] | None] = []
        crop_boxes: list[tuple[int, int, int, int] | None] = []
        masks: list[np.ndarray | None] = []
        latent_parts: list[np.ndarray] = []

        for bbox, frame_path in zip(raw_coords, frame_paths):
            frame = self.cv2.imread(frame_path)
            if frame is None:
                raise EngineError(f"MuseTalk cached frame cannot be read: {frame_path}")
            if tuple(bbox) == self.PLACEHOLDER:
                raise EngineError("Unrepaired placeholder face box in MuseTalk cache")
            x1, y1, x2, y2 = (int(v) for v in bbox)
            y2 = min(y2 + extra_margin, frame.shape[0])
            box = (x1, y1, x2, y2)
            crop = self.cv2.resize(
                frame[y1:y2, x1:x2],
                (256, 256),
                interpolation=self.cv2.INTER_LANCZOS4,
            )
            latent = self.pipe.get_latents_for_unet(crop)
            latent_parts.append(np.array(latent.astype(self.mx.float16)))
            mask, crop_box = self._exact_blend_mask(frame, box, mode=parsing_mode)
            boxes.append(box)
            masks.append(mask)
            crop_boxes.append(crop_box)

        latents = np.concatenate(latent_parts, axis=0).astype(np.float16, copy=False)
        suffix = f".tmp-{uuid.uuid4().hex}"
        latent_tmp = material_dir / f"latents-f16{suffix}.npy"
        blend_tmp = material_dir / f"blend-material{suffix}.pkl"
        manifest_tmp = material_dir / f"manifest{suffix}.json"
        try:
            np.save(latent_tmp, latents, allow_pickle=False)
            with blend_tmp.open("wb") as fh:
                pickle.dump(
                    {"boxes": boxes, "crop_boxes": crop_boxes, "masks": masks},
                    fh,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
            manifest_tmp.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest_file.unlink(missing_ok=True)
            os.replace(latent_tmp, latent_file)
            os.replace(blend_tmp, blend_file)
            os.replace(manifest_tmp, manifest_file)
        finally:
            for path in (latent_tmp, blend_tmp, manifest_tmp):
                path.unlink(missing_ok=True)

        material = MasterMaterial(
            frame_paths=frame_paths,
            boxes=boxes,
            crop_boxes=crop_boxes,
            masks=masks,
            latents=latents,
            fps=fps,
        )
        self._materials[key] = material
        self.last_material_cache_status = "built"
        return material

    def _batch_cache_file(self) -> Path:
        root = settings.workspace_dir / "cache" / "musetalk"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"best-batch-{self.variant}.json"

    def _configured_batch(self) -> int | None:
        value = os.getenv("MUSETALK_BATCH_SIZE", "auto").strip().lower()
        if value in {"", "auto"}:
            return None
        try:
            parsed = int(value)
        except ValueError as exc:
            raise EngineError(f"Invalid MUSETALK_BATCH_SIZE: {value}") from exc
        return max(1, parsed)

    def choose_batch_size(self, latents, chunks) -> int:
        explicit = self._configured_batch()
        if explicit is not None:
            return explicit
        if self._batch_size is not None:
            return self._batch_size

        cache_file = self._batch_cache_file()
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                batch = int(cached.get("batch_size") or 0)
                if batch > 0:
                    self._batch_size = batch
                    return batch
            except Exception:
                pass

        sample_n = min(64, int(latents.shape[0]))
        candidates = [32, 24, 16, 8]
        best = 8
        best_fps = 0.0
        results: list[dict[str, Any]] = []
        for batch in candidates:
            started = time.perf_counter()
            try:
                recon = self.pipe.run_batched(latents[:sample_n], chunks[:sample_n], batch_size=batch)
                elapsed = max(0.001, time.perf_counter() - started)
                fps = sample_n / elapsed
                results.append({"batch": batch, "fps": round(fps, 2)})
                del recon
                if fps > best_fps:
                    best_fps, best = fps, batch
                try:
                    self.mx.clear_cache()
                except Exception:
                    pass
            except Exception as exc:  # pragma: no cover - hardware dependent
                results.append({"batch": batch, "error": str(exc)})
                try:
                    self.mx.clear_cache()
                except Exception:
                    pass

        self._batch_size = best
        cache_file.write_text(
            json.dumps({"batch_size": best, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return best

    @staticmethod
    def _encoder() -> str:
        requested = os.getenv("MUSETALK_VIDEO_ENCODER", "auto").strip().lower()
        if requested and requested != "auto":
            return requested
        if sys.platform == "darwin":
            probe = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0 and "h264_videotoolbox" in probe.stdout:
                return "h264_videotoolbox"
        return "libx264"

    def render(
        self,
        *,
        coords_file: Path,
        audio: Path,
        output: Path,
        cache_dir: Path,
        log_file: Path | None = None,
        prepared_material: MasterMaterial | None = None,
    ) -> dict[str, Any]:
        material = prepared_material or self.prepare_master(coords_file, cache_dir)
        chunks = self.pipe.encode_audio_from_wav(audio, fps=int(round(material.fps)))
        frame_count = int(chunks.shape[0])
        if frame_count <= 0:
            raise EngineError("MuseTalk produced no audio chunks")

        indices = np.array(
            [self._cycle_index(len(material.frame_paths), i) for i in range(frame_count)],
            dtype=np.int32,
        )
        latents = self.mx.array(material.latents[indices]).astype(self.mx.float16)
        chunks = chunks.astype(self.mx.float16)
        batch_size = self.choose_batch_size(latents, chunks)

        started = time.perf_counter()
        try:
            recon = self.pipe.run_batched(latents, chunks, batch_size=batch_size)
        except Exception as first_exc:  # hardware safety fallback
            if self._configured_batch() is not None:
                raise
            recon = None
            for fallback in [24, 16, 8]:
                if fallback >= batch_size:
                    continue
                try:
                    self.mx.clear_cache()
                except Exception:
                    pass
                try:
                    recon = self.pipe.run_batched(latents, chunks, batch_size=fallback)
                    batch_size = fallback
                    self._batch_size = fallback
                    break
                except Exception:
                    continue
            if recon is None:
                raise EngineError(f"MuseTalk MLX inference failed: {first_exc}") from first_exc
        inference_seconds = time.perf_counter() - started
        encode_started = time.perf_counter()

        first_frame = self.cv2.imread(material.frame_paths[int(indices[0])])
        if first_frame is None:
            raise EngineError("Cannot read cached MuseTalk frame")
        height, width = first_frame.shape[:2]
        encoder = self._encoder()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
            "-r", f"{material.fps:.6f}", "-i", "pipe:0", "-i", str(audio),
        ]
        if encoder == "h264_videotoolbox":
            command.extend(["-c:v", encoder, "-b:v", os.getenv("MUSETALK_VT_BITRATE", "8M")])
        else:
            command.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        command.extend(["-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)])
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for i in range(frame_count):
                source_idx = int(indices[i])
                frame = self.cv2.imread(material.frame_paths[source_idx])
                if frame is None:
                    raise EngineError(f"Cannot read cached frame {source_idx}")
                box = material.boxes[source_idx]
                mask = material.masks[source_idx]
                crop_box = material.crop_boxes[source_idx]
                if box is not None and mask is not None and crop_box is not None:
                    x1, y1, x2, y2 = box
                    face = self.cv2.resize(recon[i].astype(np.uint8), (x2 - x1, y2 - y1))
                    frame = self.get_image_blending(frame, face, box, mask, crop_box)
                proc.stdin.write(frame.tobytes())
        finally:
            proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        return_code = proc.wait()
        if return_code != 0 or not output.exists():
            raise EngineError(stderr.strip() or f"FFmpeg frame pipeline failed ({return_code})")
        blend_encode_seconds = time.perf_counter() - encode_started

        if log_file:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"\n[resident-runtime] model_load={self.model_load_seconds:.2f}s "
                    f"frames={frame_count} batch={batch_size} encoder={encoder} "
                    f"inference={inference_seconds:.2f}s blend_encode={blend_encode_seconds:.2f}s "
                    f"elapsed={time.perf_counter() - started:.2f}s\n"
                )
        return {
            "resident": True,
            "batch_size": batch_size,
            "encoder": encoder,
            "frames": frame_count,
            "model_load_seconds": round(self.model_load_seconds, 2),
            "inference_seconds": round(inference_seconds, 2),
            "blend_encode_seconds": round(blend_encode_seconds, 2),
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }


_RUNTIMES: dict[str, ResidentMuseTalkRuntime] = {}


def get_resident_runtime(variant: str) -> ResidentMuseTalkRuntime:
    runtime = _RUNTIMES.get(variant)
    if runtime is None:
        runtime = ResidentMuseTalkRuntime(variant)
        _RUNTIMES[variant] = runtime
    return runtime
