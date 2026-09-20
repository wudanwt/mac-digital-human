#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


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
            raise RuntimeError("MuseTalk CUDA streaming requested NVENC but ffmpeg has no h264_nvenc")
        preset = os.getenv("VIDEO_ENCODER_NVENC_PRESET", "p4").strip() or "p4"
        return "h264_nvenc", [
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-cq", str(quality),
            "-b:v", "0",
        ]
    if mode in {"software", "x264", "libx264"}:
        return "libx264", [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(quality),
        ]
    raise RuntimeError(f"unsupported MuseTalk video encoder: {requested}")


def _prepare_alpha_patch(np, cv2, mask_array, crop_box, bbox):
    x, y, x1, y1 = [int(v) for v in bbox]
    x_s, y_s, _x_e, _y_e = [int(v) for v in crop_box]
    patch = mask_array[y - y_s:y1 - y_s, x - x_s:x1 - x_s]
    expected_h = max(0, y1 - y)
    expected_w = max(0, x1 - x)
    if patch.shape[:2] != (expected_h, expected_w):
        patch = cv2.resize(
            patch,
            (expected_w, expected_h),
            interpolation=cv2.INTER_LINEAR,
        )
    return patch.astype(np.float32, copy=False) / 255.0


def _fast_blend_frame(np, cv2, image, face, bbox, alpha_patch):
    x, y, x1, y1 = [int(v) for v in bbox]
    out = image.copy()
    height, width = out.shape[:2]
    cx0, cy0 = max(0, x), max(0, y)
    cx1, cy1 = min(width, x1), min(height, y1)
    if cx1 <= cx0 or cy1 <= cy0:
        return out

    fx0, fy0 = cx0 - x, cy0 - y
    fx1, fy1 = fx0 + (cx1 - cx0), fy0 + (cy1 - cy0)
    src = face[fy0:fy1, fx0:fx1].astype(np.float32, copy=False)
    dst = out[cy0:cy1, cx0:cx1].astype(np.float32, copy=False)
    alpha = alpha_patch[fy0:fy1, fx0:fx1]
    if alpha.shape[:2] != dst.shape[:2]:
        alpha = cv2.resize(
            alpha,
            (dst.shape[1], dst.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )
    alpha = alpha[..., None]
    blended = src * alpha + dst * (1.0 - alpha)
    out[cy0:cy1, cx0:cx1] = np.clip(blended + 0.5, 0, 255).astype(np.uint8)
    return out


def _write_metrics(path: Path, metrics: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Streaming MuseTalk 1.5 CUDA renderer")
    parser.add_argument("--musetalk-dir", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metrics-json", required=True)
    parser.add_argument("--unet-model-path", required=True)
    parser.add_argument("--unet-config", required=True)
    parser.add_argument("--whisper-dir", required=True)
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--use-float16", action="store_true")
    parser.add_argument("--extra-margin", type=int, default=10)
    parser.add_argument("--parsing-mode", default="jaw")
    parser.add_argument("--left-cheek-width", type=int, default=90)
    parser.add_argument("--right-cheek-width", type=int, default=90)
    parser.add_argument("--video-encoder", default="auto")
    parser.add_argument("--quality", type=int, default=18)
    args = parser.parse_args()
    fast_blend = os.getenv("MUSETALK_CUDA_FAST_BLEND", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }

    root = Path(args.musetalk_dir).resolve()
    video_path = Path(args.video).resolve()
    audio_path = Path(args.audio).resolve()
    output_path = Path(args.output).resolve()
    metrics_path = Path(args.metrics_json).resolve()
    if not video_path.is_file():
        raise RuntimeError(f"video not found: {video_path}")
    if not audio_path.is_file():
        raise RuntimeError(f"audio not found: {audio_path}")

    sys.path.insert(0, str(root))
    os.chdir(root)

    metrics: dict[str, object] = {}
    total_started = _timer()
    import_started = _timer()

    import cv2
    import numpy as np
    import torch
    from tqdm import tqdm
    from transformers import WhisperModel

    from musetalk.utils.audio_processor import AudioProcessor
    from musetalk.utils.blending import get_image_blending, get_image_prepare_material
    from musetalk.utils.face_parsing import FaceParsing
    from musetalk.utils.preprocessing import coord_placeholder, get_landmark_and_bbox
    from musetalk.utils.utils import datagen, get_video_fps, load_all_model

    metrics["runtime_import_seconds"] = round(_timer() - import_started, 4)
    device = torch.device(f"cuda:{args.gpu_id}" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("MuseTalk CUDA streaming runner cannot see CUDA")

    stage = _timer()
    vae, unet, pe = load_all_model(
        unet_model_path=args.unet_model_path,
        vae_type="sd-vae",
        unet_config=args.unet_config,
        device=device,
    )
    timesteps = torch.tensor([0], device=device)
    if args.use_float16:
        pe = pe.half()
        vae.vae = vae.vae.half()
        unet.model = unet.model.half()
    pe = pe.to(device)
    vae.vae = vae.vae.to(device)
    unet.model = unet.model.to(device)
    weight_dtype = unet.model.dtype
    audio_processor = AudioProcessor(feature_extractor_path=args.whisper_dir)
    whisper = WhisperModel.from_pretrained(args.whisper_dir)
    whisper = whisper.to(device=device, dtype=weight_dtype).eval()
    whisper.requires_grad_(False)
    fp = FaceParsing(
        left_cheek_width=args.left_cheek_width,
        right_cheek_width=args.right_cheek_width,
    )
    torch.cuda.synchronize(device)
    metrics["model_load_seconds"] = round(_timer() - stage, 4)

    fps = float(get_video_fps(str(video_path)))
    if fps <= 0:
        fps = 25.0

    with tempfile.TemporaryDirectory(prefix="musetalk-cuda-source-") as temp_name:
        temp_dir = Path(temp_name)
        stage = _timer()
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(video_path),
            "-start_number", "0",
            str(temp_dir / "%08d.png"),
        ])
        input_img_list = sorted(temp_dir.glob("*.png"))
        if not input_img_list:
            raise RuntimeError("MuseTalk source video produced no frames")
        metrics["source_decode_seconds"] = round(_timer() - stage, 4)
        metrics["source_frame_count"] = len(input_img_list)

        stage = _timer()
        whisper_input_features, librosa_length = audio_processor.get_audio_feature(str(audio_path))
        whisper_chunks = audio_processor.get_whisper_chunk(
            whisper_input_features,
            device,
            weight_dtype,
            whisper,
            librosa_length,
            fps=fps,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )
        torch.cuda.synchronize(device)
        metrics["audio_feature_seconds"] = round(_timer() - stage, 4)

        stage = _timer()
        coord_list, frame_list = get_landmark_and_bbox([str(p) for p in input_img_list], 0)
        metrics["landmark_seconds"] = round(_timer() - stage, 4)
        if not frame_list:
            raise RuntimeError("MuseTalk landmark preprocessing produced no frames")

        stage = _timer()
        input_latent_list = []
        adjusted_coords = []
        for bbox, frame in zip(coord_list, frame_list):
            if bbox == coord_placeholder:
                adjusted_coords.append(coord_placeholder)
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            y2 = min(frame.shape[0], y2 + args.extra_margin)
            adjusted = [x1, y1, x2, y2]
            adjusted_coords.append(adjusted)
            crop_frame = frame[y1:y2, x1:x2]
            crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            input_latent_list.append(vae.get_latents_for_unet(crop_frame))
        torch.cuda.synchronize(device)
        metrics["latent_prepare_seconds"] = round(_timer() - stage, 4)
        if not input_latent_list:
            raise RuntimeError("MuseTalk VAE preprocessing produced no usable latents")

        stage = _timer()
        blend_materials = []
        for bbox, frame in zip(adjusted_coords, frame_list):
            if bbox == coord_placeholder:
                blend_materials.append(None)
                continue
            mask_array, crop_box = get_image_prepare_material(
                frame,
                bbox,
                fp=fp,
                mode=args.parsing_mode,
            )
            alpha_patch = _prepare_alpha_patch(np, cv2, mask_array, crop_box, bbox)
            blend_materials.append((mask_array, crop_box, alpha_patch))
        metrics["blend_material_prepare_seconds"] = round(_timer() - stage, 4)

        frame_cycle = frame_list + frame_list[::-1]
        coord_cycle = adjusted_coords + adjusted_coords[::-1]
        material_cycle = blend_materials + blend_materials[::-1]
        latent_cycle = input_latent_list + input_latent_list[::-1]

        stage = _timer()
        generated_frames = []
        gen = datagen(
            whisper_chunks=whisper_chunks,
            vae_encode_latents=latent_cycle,
            batch_size=args.batch_size,
            delay_frame=0,
            device=device,
        )
        total_batches = int(np.ceil(float(len(whisper_chunks)) / args.batch_size))
        with torch.no_grad():
            for whisper_batch, latent_batch in tqdm(gen, total=total_batches, desc="CUDA inference"):
                audio_feature_batch = pe(whisper_batch)
                latent_batch = latent_batch.to(dtype=unet.model.dtype)
                pred_latents = unet.model(
                    latent_batch,
                    timesteps,
                    encoder_hidden_states=audio_feature_batch,
                ).sample
                recon = vae.decode_latents(pred_latents)
                generated_frames.extend(recon)
        torch.cuda.synchronize(device)
        metrics["unet_decode_seconds"] = round(_timer() - stage, 4)
        metrics["generated_frame_count"] = len(generated_frames)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        height, width = frame_cycle[0].shape[:2]
        encoder_name, encode_args = _encoder_args(args.video_encoder, args.quality)
        metrics["video_encoder"] = encoder_name

        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", f"{fps:.6f}",
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
            raise RuntimeError("failed to open ffmpeg rawvideo pipe")

        written = 0
        try:
            for i, res_frame in enumerate(tqdm(generated_frames, desc="Blend + stream encode")):
                cycle_index = i % len(coord_cycle)
                bbox = coord_cycle[cycle_index]
                material = material_cycle[cycle_index]
                if bbox == coord_placeholder or material is None:
                    continue
                ori_frame = frame_cycle[cycle_index].copy()
                x1, y1, x2, y2 = [int(v) for v in bbox]
                if x2 <= x1 or y2 <= y1:
                    continue
                resized = cv2.resize(
                    res_frame.astype(np.uint8),
                    (x2 - x1, y2 - y1),
                    interpolation=cv2.INTER_LINEAR,
                )
                mask_array, crop_box, alpha_patch = material
                if fast_blend:
                    combined = _fast_blend_frame(
                        np,
                        cv2,
                        ori_frame,
                        resized,
                        [x1, y1, x2, y2],
                        alpha_patch,
                    )
                else:
                    combined = get_image_blending(
                        ori_frame,
                        resized,
                        [x1, y1, x2, y2],
                        mask_array,
                        crop_box,
                    )
                proc.stdin.write(np.ascontiguousarray(combined).tobytes())
                written += 1
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        code = proc.wait()
        metrics["blend_encode_seconds"] = round(_timer() - stage, 4)
        metrics["output_frame_count"] = written
        if code != 0:
            raise RuntimeError(stderr.strip() or f"ffmpeg streaming encoder failed ({code})")
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError("MuseTalk streaming encoder produced no usable output")

    metrics["total_seconds"] = round(_timer() - total_started, 4)
    metrics["blend_backend"] = "numpy-alpha" if fast_blend else "upstream-pil"
    metrics["batch_size"] = args.batch_size
    metrics["fps"] = round(fps, 6)
    metrics["output_bytes"] = output_path.stat().st_size
    _write_metrics(metrics_path, metrics)
    print(json.dumps({"output": str(output_path), "metrics": metrics}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
