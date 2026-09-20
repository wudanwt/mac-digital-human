from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from app.config import settings

from .base import EngineError, RenderResult


class MuseTalkCUDAEngine:
    """Official MuseTalk 1.5 PyTorch/CUDA backend for Linux NVIDIA workers.

    The V2 CUDA path keeps the model implementation isolated from the Apple
    Silicon MLX runtime while replacing MuseTalk's PNG result spool with a
    rawvideo -> FFmpeg streaming encoder. Set MUSETALK_CUDA_STREAMING=0 to
    fall back to the untouched upstream inference entrypoint.
    """

    name = "musetalk"
    backend = "cuda"

    def __init__(self) -> None:
        settings.ensure_runtime_dirs()
        self.repo = Path(
            os.getenv(
                "MUSETALK_CUDA_DIR",
                str(settings.root / "vendor" / "MuseTalk-CUDA"),
            )
        ).expanduser().resolve()
        self.conda_env = os.getenv("MUSETALK_CONDA_ENV", "musetalk-cuda").strip()
        self.gpu_id = max(0, int(os.getenv("MUSETALK_CUDA_GPU_ID", "0")))
        self.batch_size = max(1, int(os.getenv("MUSETALK_CUDA_BATCH_SIZE", "8")))
        self.use_float16 = os.getenv("MUSETALK_CUDA_FP16", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self.streaming = os.getenv("MUSETALK_CUDA_STREAMING", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self.video_encoder = os.getenv("MUSETALK_CUDA_VIDEO_ENCODER", "auto").strip() or "auto"
        self.streaming_runner = settings.root / "scripts" / "cloud" / "musetalk_cuda_stream.py"

    def _python_prefix(self) -> list[str]:
        explicit = os.getenv("MUSETALK_CUDA_PYTHON", "").strip()
        if explicit:
            return [explicit]
        candidates = [
            settings.root / ".venv-musetalk-cuda" / "bin" / "python",
            self.repo.parent / ".venv-musetalk-cuda" / "bin" / "python",
            self.repo / ".venv" / "bin" / "python",
        ]
        for path in candidates:
            if path.is_file() and os.access(path, os.X_OK):
                return [str(path)]
        conda = shutil.which("conda")
        if conda and self.conda_env:
            return [conda, "run", "--no-capture-output", "-n", self.conda_env, "python"]
        return []

    def _cuda_probe(self) -> dict[str, object]:
        prefix = self._python_prefix()
        if not prefix:
            return {"ready": False, "error": "CUDA Python runtime is not configured"}
        code = (
            "import json, torch; "
            "ok=bool(torch.cuda.is_available()); "
            "print(json.dumps({"
            "'ready':ok,"
            "'torch':str(torch.__version__),"
            "'cuda':str(torch.version.cuda or ''),"
            "'gpu':torch.cuda.get_device_name(0) if ok else '',"
            "'vram_bytes':int(torch.cuda.get_device_properties(0).total_memory) if ok else 0"
            "}))"
        )
        try:
            proc = subprocess.run(
                [*prefix, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ready": False, "error": str(exc)}
        if proc.returncode != 0:
            return {
                "ready": False,
                "error": (proc.stderr or proc.stdout or "CUDA probe failed").strip(),
            }
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            return {"ready": False, "error": proc.stdout.strip() or "invalid CUDA probe output"}
        return payload if isinstance(payload, dict) else {"ready": False, "error": "invalid CUDA probe output"}

    def readiness(self, variant: str | None = None) -> dict[str, object]:
        model_dir = self.repo / "models" / "musetalkV15"
        checks: dict[str, bool] = {
            "linux": platform.system() == "Linux",
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "nvidia_smi": shutil.which("nvidia-smi") is not None,
            "cuda_repo": (self.repo / "scripts" / "inference.py").is_file(),
            "unet": (model_dir / "unet.pth").is_file(),
            "unet_config": (model_dir / "musetalk.json").is_file(),
            "whisper": (self.repo / "models" / "whisper" / "pytorch_model.bin").is_file(),
            "vae": (self.repo / "models" / "sd-vae" / "diffusion_pytorch_model.bin").is_file(),
            "python_runtime": bool(self._python_prefix()),
        }
        if self.streaming:
            checks["streaming_runner"] = self.streaming_runner.is_file()
        probe = self._cuda_probe() if checks["python_runtime"] else {"ready": False}
        checks["torch_cuda"] = bool(probe.get("ready"))
        return {
            "engine": self.name,
            "backend": self.backend,
            "ready": all(checks.values()),
            "variant": "v1.5",
            "requested_variant": variant or settings.default_musetalk_variant,
            "gpu_id": self.gpu_id,
            "batch_size": self.batch_size,
            "float16": self.use_float16,
            "streaming": self.streaming,
            "video_encoder": self.video_encoder,
            "checks": checks,
            "cuda": probe,
        }

    @staticmethod
    def _run(cmd: list[str], *, cwd: Path, log_file: Path) -> None:
        with log_file.open("a", encoding="utf-8") as log:
            log.write("\n$ " + " ".join(cmd) + "\n")
            log.flush()
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if proc.returncode != 0:
            raise EngineError(
                f"MuseTalk CUDA command failed ({proc.returncode}); inspect {log_file}"
            )

    @staticmethod
    def _yaml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _render_upstream(
        self,
        *,
        prefix: list[str],
        video: Path,
        audio: Path,
        work: Path,
        log_file: Path,
        final: Path,
    ) -> dict[str, object]:
        result_root = work / "cuda-results"
        result_root.mkdir(parents=True, exist_ok=True)
        config_path = work / "musetalk-cuda.yaml"
        config_path.write_text(
            "task:\n"
            f"  video_path: {self._yaml_string(str(video))}\n"
            f"  audio_path: {self._yaml_string(str(audio))}\n"
            '  result_name: "result.mp4"\n',
            encoding="utf-8",
        )
        command = [
            *prefix,
            "-m",
            "scripts.inference",
            "--inference_config",
            str(config_path),
            "--result_dir",
            str(result_root),
            "--unet_model_path",
            str(self.repo / "models" / "musetalkV15" / "unet.pth"),
            "--unet_config",
            str(self.repo / "models" / "musetalkV15" / "musetalk.json"),
            "--whisper_dir",
            str(self.repo / "models" / "whisper"),
            "--version",
            "v15",
            "--gpu_id",
            str(self.gpu_id),
            "--batch_size",
            str(self.batch_size),
        ]
        if self.use_float16:
            command.append("--use_float16")
        self._run(command, cwd=self.repo, log_file=log_file)
        generated = result_root / "v15" / "result.mp4"
        if not generated.is_file() or generated.stat().st_size <= 0:
            raise EngineError(
                "MuseTalk CUDA inference returned without a usable result; "
                f"inspect {log_file}"
            )
        shutil.copy2(generated, final)
        return {"pipeline": "upstream-png", "video_encoder": "libx264"}

    def _render_streaming(
        self,
        *,
        prefix: list[str],
        video: Path,
        audio: Path,
        work: Path,
        log_file: Path,
        final: Path,
    ) -> dict[str, object]:
        metrics_path = work / "cuda-performance.json"
        command = [
            *prefix,
            str(self.streaming_runner),
            "--musetalk-dir",
            str(self.repo),
            "--video",
            str(video),
            "--audio",
            str(audio),
            "--output",
            str(final),
            "--metrics-json",
            str(metrics_path),
            "--unet-model-path",
            str(self.repo / "models" / "musetalkV15" / "unet.pth"),
            "--unet-config",
            str(self.repo / "models" / "musetalkV15" / "musetalk.json"),
            "--whisper-dir",
            str(self.repo / "models" / "whisper"),
            "--gpu-id",
            str(self.gpu_id),
            "--batch-size",
            str(self.batch_size),
            "--video-encoder",
            self.video_encoder,
        ]
        if self.use_float16:
            command.append("--use-float16")
        self._run(command, cwd=self.repo, log_file=log_file)
        if not final.is_file() or final.stat().st_size <= 0:
            raise EngineError(
                "MuseTalk CUDA streaming inference returned without a usable result; "
                f"inspect {log_file}"
            )
        timings: dict[str, object] = {}
        if metrics_path.is_file():
            try:
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    timings = payload
            except Exception:
                timings = {}
        return {
            "pipeline": "streaming-v2",
            "video_encoder": timings.get("video_encoder") or self.video_encoder,
            "cuda_timings": timings,
        }

    def render(
        self,
        video: Path,
        audio: Path,
        variant: str | None = None,
        output: Path | None = None,
        job_id: str | None = None,
        master_cache_key: str | None = None,
    ) -> RenderResult:
        status = self.readiness(variant)
        if not status["ready"]:
            missing = [name for name, ok in status["checks"].items() if not ok]
            detail = str((status.get("cuda") or {}).get("error") or "")
            suffix = f"; {detail}" if detail else ""
            raise EngineError(
                "MuseTalk CUDA backend is not ready; missing: "
                + ", ".join(missing)
                + suffix
            )

        video = Path(video).resolve()
        audio = Path(audio).resolve()
        if not video.is_file():
            raise EngineError(f"video not found: {video}")
        if not audio.is_file():
            raise EngineError(f"audio not found: {audio}")

        job_id = job_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        work = settings.workspace_dir / job_id
        work.mkdir(parents=True, exist_ok=True)
        log_file = work / "render.log"
        final = (
            Path(output).resolve()
            if output is not None
            else (settings.outputs_dir / job_id / "result.mp4").resolve()
        )
        final.parent.mkdir(parents=True, exist_ok=True)

        prefix = self._python_prefix()
        started = time.time()
        if self.streaming:
            performance = self._render_streaming(
                prefix=prefix,
                video=video,
                audio=audio,
                work=work,
                log_file=log_file,
                final=final,
            )
        else:
            performance = self._render_upstream(
                prefix=prefix,
                video=video,
                audio=audio,
                work=work,
                log_file=log_file,
                final=final,
            )
        elapsed = time.time() - started

        metadata = {
            "job_id": job_id,
            "engine": self.name,
            "backend": self.backend,
            "model_family": "musetalk-1.5",
            "video": str(video),
            "audio": str(audio),
            "output": str(final),
            "gpu_id": self.gpu_id,
            "batch_size": self.batch_size,
            "float16": self.use_float16,
            "master_cache_key": master_cache_key,
            "elapsed_seconds": round(elapsed, 3),
            **performance,
        }
        (work / "job.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return RenderResult(
            job_id=job_id,
            output=final,
            workspace=work,
            elapsed_seconds=elapsed,
            engine=self.name,
            metadata=metadata,
        )
