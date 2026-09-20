#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PROTOCOL_OUT = sys.stdout


def _timer() -> float:
    return time.perf_counter()


def _run(command: list[str]) -> None:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "command failed")


def _ffmpeg_has_encoder(name: str) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or name not in (proc.stdout + proc.stderr):
        return False
    if name != "h264_nvenc":
        return True
    probe = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:r=25:d=0.04",
            "-frames:v", "1", "-c:v", "h264_nvenc",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def _encoder_args(requested: str, quality: int) -> tuple[str, list[str]]:
    mode = requested.strip().lower()
    if mode in {"", "auto"}:
        mode = "nvenc" if _ffmpeg_has_encoder("h264_nvenc") else "libx264"
    if mode in {"nvenc", "h264_nvenc"}:
        if not _ffmpeg_has_encoder("h264_nvenc"):
            raise RuntimeError("resident MuseTalk requested NVENC but ffmpeg cannot use h264_nvenc")
        preset = os.getenv("VIDEO_ENCODER_NVENC_PRESET", "p4").strip() or "p4"
        return "h264_nvenc", [
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-cq", str(int(quality)),
            "-b:v", "0",
        ]
    if mode in {"software", "x264", "libx264"}:
        return "libx264", [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(int(quality)),
        ]
    raise RuntimeError(f"unsupported video encoder: {requested}")


@dataclass
class MasterMaterial:
    key: str
    source: str
    source_size: int
    source_mtime_ns: int
    fps: float
    frames: list[Any]
    coords: list[Any]
    latents: list[Any]
    blend_materials: list[Any]
    width: int
    height: int
    prepared_at: float
    prepare_metrics: dict[str, float]
    estimated_cpu_bytes: int
    estimated_gpu_bytes: int


class ResidentMuseTalkRuntime:
    def __init__(
        self,
        *,
        musetalk_dir: Path,
        unet_model_path: Path,
        unet_config: Path,
        whisper_dir: Path,
        gpu_id: int,
        use_float16: bool,
        parsing_mode: str,
        left_cheek_width: int,
        right_cheek_width: int,
        extra_margin: int,
        cache_items: int,
        cache_cpu_gb: float,
        cache_gpu_gb: float,
    ) -> None:
        self.root = musetalk_dir.resolve()
        self.gpu_id = gpu_id
        self.use_float16 = use_float16
        self.parsing_mode = parsing_mode
        self.extra_margin = extra_margin
        self.cache_items = max(1, cache_items)
        self.cache_cpu_bytes = max(0, int(cache_cpu_gb * 1024**3))
        self.cache_gpu_bytes = max(0, int(cache_gpu_gb * 1024**3))
        self.started_at = time.time()
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_evictions = 0
        self.master_cache: OrderedDict[str, MasterMaterial] = OrderedDict()

        sys.path.insert(0, str(self.root))
        os.chdir(self.root)

        import_started = _timer()
        import cv2
        import numpy as np
        import torch
        from transformers import WhisperModel

        from musetalk.utils.audio_processor import AudioProcessor
        from musetalk.utils.blending import get_image_blending, get_image_prepare_material
        from musetalk.utils.face_parsing import FaceParsing
        from musetalk.utils.preprocessing import coord_placeholder, get_landmark_and_bbox
        from musetalk.utils.utils import datagen, get_video_fps, load_all_model

        self.cv2 = cv2
        self.np = np
        self.torch = torch
        self.WhisperModel = WhisperModel
        self.AudioProcessor = AudioProcessor
        self.get_image_blending = get_image_blending
        self.get_image_prepare_material = get_image_prepare_material
        self.FaceParsing = FaceParsing
        self.coord_placeholder = coord_placeholder
        self.get_landmark_and_bbox = get_landmark_and_bbox
        self.datagen = datagen
        self.get_video_fps = get_video_fps
        self.load_all_model = load_all_model
        self.runtime_import_seconds = _timer() - import_started

        self.device = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")
        if self.device.type != "cuda":
            raise RuntimeError("MuseTalk resident runtime cannot see CUDA")

        stage = _timer()
        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=str(unet_model_path),
            vae_type="sd-vae",
            unet_config=str(unet_config),
            device=self.device,
        )
        self.timesteps = torch.tensor([0], device=self.device)
        if use_float16:
            self.pe = self.pe.half()
            self.vae.vae = self.vae.vae.half()
            self.unet.model = self.unet.model.half()
        self.pe = self.pe.to(self.device)
        self.vae.vae = self.vae.vae.to(self.device)
        self.unet.model = self.unet.model.to(self.device)
        self.weight_dtype = self.unet.model.dtype

        self.audio_processor = AudioProcessor(feature_extractor_path=str(whisper_dir))
        self.whisper = WhisperModel.from_pretrained(str(whisper_dir))
        self.whisper = self.whisper.to(device=self.device, dtype=self.weight_dtype).eval()
        self.whisper.requires_grad_(False)
        self.fp = FaceParsing(
            left_cheek_width=left_cheek_width,
            right_cheek_width=right_cheek_width,
        )
        torch.cuda.synchronize(self.device)
        self.model_load_seconds = _timer() - stage

    def _source_signature(self, path: Path) -> tuple[int, int]:
        stat = path.stat()
        return int(stat.st_size), int(stat.st_mtime_ns)

    def _estimate_gpu_bytes(self, latents: list[Any]) -> int:
        total = 0
        for tensor in latents:
            try:
                total += int(tensor.numel() * tensor.element_size())
            except Exception:
                pass
        return total

    def _estimate_cpu_bytes(self, frames: list[Any], blend_materials: list[Any]) -> int:
        total = 0
        for frame in frames:
            total += int(getattr(frame, "nbytes", 0))
        for material in blend_materials:
            if material is None:
                continue
            mask, _crop = material
            total += int(getattr(mask, "nbytes", 0))
        return total

    def _cache_usage(self) -> tuple[int, int]:
        cpu = sum(item.estimated_cpu_bytes for item in self.master_cache.values())
        gpu = sum(item.estimated_gpu_bytes for item in self.master_cache.values())
        return cpu, gpu

    def _evict_if_needed(self) -> None:
        evicted = False
        while len(self.master_cache) > 1:
            cpu, gpu = self._cache_usage()
            over_items = len(self.master_cache) > self.cache_items
            over_cpu = self.cache_cpu_bytes > 0 and cpu > self.cache_cpu_bytes
            over_gpu = self.cache_gpu_bytes > 0 and gpu > self.cache_gpu_bytes
            if not (over_items or over_cpu or over_gpu):
                break
            _key, material = self.master_cache.popitem(last=False)
            self.cache_evictions += 1
            evicted = True
            del material
        if evicted and self.device.type == "cuda":
            self.torch.cuda.empty_cache()

    def clear_cache(self) -> dict[str, Any]:
        entries = len(self.master_cache)
        self.master_cache.clear()
        if self.device.type == "cuda":
            self.torch.cuda.empty_cache()
        return {"cleared_entries": entries}

    def _prepare_master(self, video_path: Path, cache_key: str) -> tuple[MasterMaterial, bool, dict[str, float]]:
        size, mtime_ns = self._source_signature(video_path)
        cached = self.master_cache.get(cache_key)
        if (
            cached is not None
            and cached.source == str(video_path)
            and cached.source_size == size
            and cached.source_mtime_ns == mtime_ns
        ):
            self.cache_hits += 1
            self.master_cache.move_to_end(cache_key)
            return cached, True, {
                "source_decode_seconds": 0.0,
                "landmark_seconds": 0.0,
                "latent_prepare_seconds": 0.0,
                "blend_material_prepare_seconds": 0.0,
                "master_prepare_seconds": 0.0,
            }

        self.cache_misses += 1
        stage_all = _timer()
        metrics: dict[str, float] = {}

        fps = float(self.get_video_fps(str(video_path)))
        if fps <= 0:
            fps = 25.0

        with tempfile.TemporaryDirectory(prefix="musetalk-cuda-master-") as temp_name:
            temp_dir = Path(temp_name)
            stage = _timer()
            _run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(video_path),
                "-start_number", "0",
                str(temp_dir / "%08d.png"),
            ])
            image_paths = sorted(temp_dir.glob("*.png"))
            if not image_paths:
                raise RuntimeError("MuseTalk master video produced no frames")
            metrics["source_decode_seconds"] = _timer() - stage

            stage = _timer()
            coord_list, frame_list = self.get_landmark_and_bbox([str(p) for p in image_paths], 0)
            metrics["landmark_seconds"] = _timer() - stage
            if not frame_list:
                raise RuntimeError("MuseTalk master preprocessing produced no frames")

        stage = _timer()
        latents: list[Any] = []
        adjusted_coords: list[Any] = []
        for bbox, frame in zip(coord_list, frame_list):
            if bbox == self.coord_placeholder:
                adjusted_coords.append(self.coord_placeholder)
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            y2 = min(frame.shape[0], y2 + self.extra_margin)
            if x2 <= x1 or y2 <= y1:
                adjusted_coords.append(self.coord_placeholder)
                continue
            adjusted = [x1, y1, x2, y2]
            adjusted_coords.append(adjusted)
            crop_frame = frame[y1:y2, x1:x2]
            crop_frame = self.cv2.resize(
                crop_frame,
                (256, 256),
                interpolation=self.cv2.INTER_LANCZOS4,
            )
            latents.append(self.vae.get_latents_for_unet(crop_frame))
        self.torch.cuda.synchronize(self.device)
        metrics["latent_prepare_seconds"] = _timer() - stage
        if not latents:
            raise RuntimeError("MuseTalk master VAE preprocessing produced no usable latents")

        stage = _timer()
        blend_materials: list[Any] = []
        for bbox, frame in zip(adjusted_coords, frame_list):
            if bbox == self.coord_placeholder:
                blend_materials.append(None)
                continue
            mask_array, crop_box = self.get_image_prepare_material(
                frame,
                bbox,
                fp=self.fp,
                mode=self.parsing_mode,
            )
            blend_materials.append((mask_array, crop_box))
        metrics["blend_material_prepare_seconds"] = _timer() - stage
        metrics["master_prepare_seconds"] = _timer() - stage_all

        height, width = frame_list[0].shape[:2]
        material = MasterMaterial(
            key=cache_key,
            source=str(video_path),
            source_size=size,
            source_mtime_ns=mtime_ns,
            fps=fps,
            frames=frame_list,
            coords=adjusted_coords,
            latents=latents,
            blend_materials=blend_materials,
            width=int(width),
            height=int(height),
            prepared_at=time.time(),
            prepare_metrics={k: float(v) for k, v in metrics.items()},
            estimated_cpu_bytes=self._estimate_cpu_bytes(frame_list, blend_materials),
            estimated_gpu_bytes=self._estimate_gpu_bytes(latents),
        )
        self.master_cache[cache_key] = material
        self.master_cache.move_to_end(cache_key)
        self._evict_if_needed()
        return material, False, metrics

    def _audio_features(self, audio_path: Path, fps: float) -> tuple[list[Any], float]:
        stage = _timer()
        features, librosa_length = self.audio_processor.get_audio_feature(str(audio_path))
        chunks = self.audio_processor.get_whisper_chunk(
            features,
            self.device,
            self.weight_dtype,
            self.whisper,
            librosa_length,
            fps=fps,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )
        self.torch.cuda.synchronize(self.device)
        return chunks, _timer() - stage

    def render(
        self,
        *,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        cache_key: str,
        batch_size: int,
        video_encoder: str,
        quality: int,
    ) -> dict[str, Any]:
        total_started = _timer()
        material, cache_hit, prepare_metrics = self._prepare_master(video_path, cache_key)
        whisper_chunks, audio_feature_seconds = self._audio_features(audio_path, material.fps)

        frame_cycle = material.frames + material.frames[::-1]
        coord_cycle = material.coords + material.coords[::-1]
        blend_cycle = material.blend_materials + material.blend_materials[::-1]
        latent_cycle = material.latents + material.latents[::-1]

        stage = _timer()
        generated_frames: list[Any] = []
        gen = self.datagen(
            whisper_chunks=whisper_chunks,
            vae_encode_latents=latent_cycle,
            batch_size=batch_size,
            delay_frame=0,
            device=self.device,
        )
        total_batches = int(self.np.ceil(float(len(whisper_chunks)) / batch_size))
        with self.torch.inference_mode():
            for _index, (whisper_batch, latent_batch) in enumerate(gen):
                audio_feature_batch = self.pe(whisper_batch)
                latent_batch = latent_batch.to(dtype=self.unet.model.dtype)
                pred_latents = self.unet.model(
                    latent_batch,
                    self.timesteps,
                    encoder_hidden_states=audio_feature_batch,
                ).sample
                recon = self.vae.decode_latents(pred_latents)
                generated_frames.extend(recon)
        self.torch.cuda.synchronize(self.device)
        unet_decode_seconds = _timer() - stage

        output_path.parent.mkdir(parents=True, exist_ok=True)
        encoder_name, encode_args = _encoder_args(video_encoder, quality)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{material.width}x{material.height}",
            "-r", f"{material.fps:.6f}",
            "-i", "pipe:0",
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0?",
            *encode_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]

        stage = _timer()
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if proc.stdin is None:
            raise RuntimeError("failed to open resident FFmpeg rawvideo pipe")

        written = 0
        try:
            for i, res_frame in enumerate(generated_frames):
                cycle_index = i % len(coord_cycle)
                bbox = coord_cycle[cycle_index]
                blend_material = blend_cycle[cycle_index]
                if bbox == self.coord_placeholder or blend_material is None:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                if x2 <= x1 or y2 <= y1:
                    continue
                resized = self.cv2.resize(
                    res_frame.astype(self.np.uint8),
                    (x2 - x1, y2 - y1),
                    interpolation=self.cv2.INTER_LINEAR,
                )
                mask_array, crop_box = blend_material
                combined = self.get_image_blending(
                    frame_cycle[cycle_index].copy(),
                    resized,
                    [x1, y1, x2, y2],
                    mask_array,
                    crop_box,
                )
                proc.stdin.write(self.np.ascontiguousarray(combined).tobytes())
                written += 1
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        code = proc.wait()
        blend_encode_seconds = _timer() - stage
        if code != 0:
            raise RuntimeError(stderr.strip() or f"resident FFmpeg encoder failed ({code})")
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("resident MuseTalk produced no usable output")

        cached_cpu, cached_gpu = self._cache_usage()
        return {
            "pipeline": "resident-v3",
            "resident": True,
            "resident_pid": os.getpid(),
            "resident_uptime_seconds": round(time.time() - self.started_at, 3),
            "runtime_import_seconds": round(self.runtime_import_seconds, 4),
            "resident_model_load_seconds": round(self.model_load_seconds, 4),
            "model_load_seconds": 0.0,
            "master_cache_key": cache_key,
            "master_cache_hit": cache_hit,
            "master_cache_entries": len(self.master_cache),
            "master_cache_hits_total": self.cache_hits,
            "master_cache_misses_total": self.cache_misses,
            "master_cache_evictions_total": self.cache_evictions,
            "master_cache_cpu_mb": round(cached_cpu / 1024**2, 2),
            "master_cache_gpu_mb": round(cached_gpu / 1024**2, 2),
            "master_cache_cpu_limit_gb": round(self.cache_cpu_bytes / 1024**3, 2),
            "master_cache_gpu_limit_gb": round(self.cache_gpu_bytes / 1024**3, 2),
            "source_decode_seconds": round(float(prepare_metrics["source_decode_seconds"]), 4),
            "landmark_seconds": round(float(prepare_metrics["landmark_seconds"]), 4),
            "latent_prepare_seconds": round(float(prepare_metrics["latent_prepare_seconds"]), 4),
            "blend_material_prepare_seconds": round(
                float(prepare_metrics["blend_material_prepare_seconds"]), 4
            ),
            "master_prepare_seconds": round(float(prepare_metrics["master_prepare_seconds"]), 4),
            "audio_feature_seconds": round(audio_feature_seconds, 4),
            "unet_decode_seconds": round(unet_decode_seconds, 4),
            "blend_encode_seconds": round(blend_encode_seconds, 4),
            "generated_frame_count": len(generated_frames),
            "output_frame_count": written,
            "source_frame_count": len(material.frames),
            "video_encoder": encoder_name,
            "batch_size": batch_size,
            "fps": round(material.fps, 6),
            "output_bytes": output_path.stat().st_size,
            "total_seconds": round(_timer() - total_started, 4),
        }

    def stats(self) -> dict[str, Any]:
        cached_cpu, cached_gpu = self._cache_usage()
        return {
            "pid": os.getpid(),
            "uptime_seconds": round(time.time() - self.started_at, 3),
            "cache_entries": len(self.master_cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_evictions": self.cache_evictions,
            "cache_cpu_mb": round(cached_cpu / 1024**2, 2),
            "cache_gpu_mb": round(cached_gpu / 1024**2, 2),
            "cache_cpu_limit_gb": round(self.cache_cpu_bytes / 1024**3, 2),
            "cache_gpu_limit_gb": round(self.cache_gpu_bytes / 1024**3, 2),
            "gpu_allocated_mb": round(self.torch.cuda.memory_allocated(self.device) / 1024**2, 2),
            "gpu_reserved_mb": round(self.torch.cuda.memory_reserved(self.device) / 1024**2, 2),
        }


def _emit(payload: dict[str, Any]) -> None:
    _PROTOCOL_OUT.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _PROTOCOL_OUT.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Resident MuseTalk CUDA runtime")
    parser.add_argument("--musetalk-dir", required=True)
    parser.add_argument("--unet-model-path", required=True)
    parser.add_argument("--unet-config", required=True)
    parser.add_argument("--whisper-dir", required=True)
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--use-float16", action="store_true")
    parser.add_argument("--extra-margin", type=int, default=10)
    parser.add_argument("--parsing-mode", default="jaw")
    parser.add_argument("--left-cheek-width", type=int, default=90)
    parser.add_argument("--right-cheek-width", type=int, default=90)
    parser.add_argument("--cache-items", type=int, default=2)
    parser.add_argument("--cache-cpu-gb", type=float, default=6.0)
    parser.add_argument("--cache-gpu-gb", type=float, default=4.0)
    args = parser.parse_args()

    # Keep stdout as a clean JSON-lines control channel. MuseTalk, mmpose,
    # transformers and tqdm are free to print diagnostics to stderr.
    sys.stdout = sys.stderr

    try:
        runtime = ResidentMuseTalkRuntime(
            musetalk_dir=Path(args.musetalk_dir),
            unet_model_path=Path(args.unet_model_path),
            unet_config=Path(args.unet_config),
            whisper_dir=Path(args.whisper_dir),
            gpu_id=args.gpu_id,
            use_float16=args.use_float16,
            parsing_mode=args.parsing_mode,
            left_cheek_width=args.left_cheek_width,
            right_cheek_width=args.right_cheek_width,
            extra_margin=args.extra_margin,
            cache_items=args.cache_items,
            cache_cpu_gb=args.cache_cpu_gb,
            cache_gpu_gb=args.cache_gpu_gb,
        )
    except Exception as exc:
        _emit({
            "event": "fatal",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        return 2

    _emit({
        "event": "ready",
        "pid": os.getpid(),
        "runtime_import_seconds": round(runtime.runtime_import_seconds, 4),
        "model_load_seconds": round(runtime.model_load_seconds, 4),
        "gpu": runtime.torch.cuda.get_device_name(runtime.device),
        "cache_items": runtime.cache_items,
        "cache_cpu_limit_gb": round(runtime.cache_cpu_bytes / 1024**3, 2),
        "cache_gpu_limit_gb": round(runtime.cache_gpu_bytes / 1024**3, 2),
    })

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request_id = ""
        try:
            request = json.loads(raw)
            request_id = str(request.get("id") or "")
            command = str(request.get("command") or "render")
            if command == "render":
                metrics = runtime.render(
                    video_path=Path(str(request["video"])).resolve(),
                    audio_path=Path(str(request["audio"])).resolve(),
                    output_path=Path(str(request["output"])).resolve(),
                    cache_key=str(request["master_cache_key"]),
                    batch_size=max(1, int(request.get("batch_size") or 8)),
                    video_encoder=str(request.get("video_encoder") or "auto"),
                    quality=int(request.get("quality") or 18),
                )
                _emit({"id": request_id, "ok": True, "metrics": metrics})
            elif command == "stats":
                _emit({"id": request_id, "ok": True, "stats": runtime.stats()})
            elif command == "clear_cache":
                _emit({"id": request_id, "ok": True, **runtime.clear_cache()})
            elif command == "shutdown":
                _emit({"id": request_id, "ok": True, "event": "shutdown"})
                return 0
            else:
                raise ValueError(f"unsupported resident command: {command}")
        except Exception as exc:
            _emit({
                "id": request_id,
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
