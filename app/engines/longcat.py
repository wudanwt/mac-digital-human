from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app.config import settings

from .base import EngineError, RenderResult


LONGCAT_VARIANT_DIRS = {
    "q4-merged": "LongCat-Video-Avatar-1.5-q4-dmd-merged",
    "q8-merged": "LongCat-Video-Avatar-1.5-q8-dmd-merged",
    "merged": "LongCat-Video-Avatar-1.5-bf16-dmd-merged",
}


class LongCatMLXEngine:
    """High-quality image+audio avatar generation using LongCat Avatar 1.5 MLX.

    The current upstream MLX port is a single-clip AI2V pipeline. It is suitable
    for premium intros / short presenter clips, not realtime generation.
    """

    name = "longcat"

    def __init__(self) -> None:
        settings.ensure_runtime_dirs()

    def readiness(self, variant: str | None = None) -> dict:
        variant = variant or settings.default_longcat_variant
        variant_dirname = LONGCAT_VARIANT_DIRS.get(variant)
        model_dir = settings.longcat_weights_dir / variant_dirname if variant_dirname else None
        whisper_fe = settings.longcat_weights_dir / "whisper-large-v3-feature-extractor"
        checks = {
            "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "longcat_mlx_repo": (settings.longcat_mlx_dir / "longcat_video_avatar").exists(),
            "upstream_inference_script": (settings.longcat_mlx_dir / "scripts" / "run_inference.py").exists(),
            "adapter_script": settings.longcat_adapter_script.exists(),
            "variant_supported": variant_dirname is not None,
            "model_dir": bool(model_dir and (model_dir / "dit" / "config.json").exists()),
            "tokenizer": bool(model_dir and (model_dir / "tokenizer").exists()),
            "audio_encoder": bool(model_dir and (model_dir / "audio_encoder" / "config.json").exists()),
            "text_encoder": bool(model_dir and (model_dir / "text_encoder" / "config.json").exists()),
            "vae": bool(model_dir and (model_dir / "vae" / "config.json").exists()),
            "whisper_feature_extractor": (whisper_fe / "preprocessor_config.json").exists(),
        }
        return {
            "engine": self.name,
            "ready": all(checks.values()),
            "variant": variant,
            "checks": checks,
            "notes": [
                "M5 Pro 48GB: q4-merged is the recommended variant.",
                "Current MLX port generates one short clip per job; long-video continuation is not yet integrated.",
            ],
        }

    @staticmethod
    def _run(cmd: list[str], cwd: Path | None = None, log_file: Path | None = None) -> None:
        if log_file:
            with log_file.open("a", encoding="utf-8") as log:
                log.write("\n$ " + " ".join(cmd) + "\n")
                log.flush()
                proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        else:
            proc = subprocess.run(cmd, cwd=cwd)
        if proc.returncode != 0:
            raise EngineError(f"command failed ({proc.returncode}): {' '.join(cmd)}")

    def render(
        self,
        image: Path,
        audio: Path,
        prompt: str,
        variant: str | None = None,
        height: int | None = None,
        width: int | None = None,
        num_frames: int | None = None,
        seed: int = 42,
        output: Path | None = None,
        job_id: str | None = None,
    ) -> RenderResult:
        variant = variant or settings.default_longcat_variant
        height = height or settings.longcat_height
        width = width or settings.longcat_width
        num_frames = num_frames or settings.longcat_num_frames

        status = self.readiness(variant)
        if not status["ready"]:
            missing = [k for k, ok in status["checks"].items() if not ok]
            raise EngineError("LongCat engine is not ready; missing: " + ", ".join(missing))
        if not image.exists():
            raise EngineError(f"image not found: {image}")
        if not audio.exists():
            raise EngineError(f"audio not found: {audio}")
        if not prompt.strip():
            raise EngineError("LongCat prompt must not be empty")
        if height % 8 or width % 8:
            raise EngineError("LongCat height and width must be divisible by 8")
        if num_frames < 9 or (num_frames - 1) % 4 != 0:
            raise EngineError("LongCat num_frames must satisfy 4n+1 and be at least 9")

        job_id = job_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        work = settings.workspace_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        log = work / "render.log"
        normalized_audio = work / "voice_16k.wav"
        final = output or (settings.outputs_dir / job_id / "result.mp4")
        final.parent.mkdir(parents=True, exist_ok=True)

        started = time.time()
        self._run(
            [
                "ffmpeg", "-y", "-i", str(audio), "-vn", "-ar", "16000", "-ac", "1",
                "-c:a", "pcm_s16le", str(normalized_audio),
            ],
            log_file=log,
        )

        self._run(
            [
                sys.executable,
                str(settings.longcat_adapter_script),
                "--vendor", str(settings.longcat_mlx_dir),
                "--weights", str(settings.longcat_weights_dir),
                "--variant", variant,
                "--image", str(image),
                "--audio", str(normalized_audio),
                "--prompt", prompt,
                "--height", str(height),
                "--width", str(width),
                "--num-frames", str(num_frames),
                "--seed", str(seed),
                "--fps", str(settings.longcat_fps),
                "--out", str(final),
            ],
            cwd=settings.root,
            log_file=log,
        )

        if not final.exists():
            raise EngineError("LongCat inference completed without producing the expected MP4")

        elapsed = time.time() - started
        metadata = {
            "job_id": job_id,
            "engine": self.name,
            "image": str(image),
            "audio": str(audio),
            "prompt": prompt,
            "variant": variant,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "fps": settings.longcat_fps,
            "seed": seed,
            "output": str(final),
            "elapsed_seconds": round(elapsed, 2),
        }
        (work / "job.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return RenderResult(
            job_id=job_id,
            output=final,
            workspace=work,
            elapsed_seconds=elapsed,
            engine=self.name,
            metadata=metadata,
        )
