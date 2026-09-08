from __future__ import annotations

import json
import pickle
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import settings


class EngineError(RuntimeError):
    pass


@dataclass
class RenderResult:
    job_id: str
    output: Path
    workspace: Path
    elapsed_seconds: float


class MuseTalkMLXEngine:
    """Thin orchestration layer around the pinned musetalk-mlx integration scripts."""

    PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)

    def __init__(self) -> None:
        settings.ensure_runtime_dirs()

    def readiness(self, variant: str | None = None) -> dict:
        variant = variant or settings.default_variant
        mlx = settings.musetalk_mlx_dir
        upstream = settings.musetalk_upstream_dir
        model_dir = mlx / "dist" / f"MuseTalk-1.5-MLX-{variant}"
        checks = {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "musetalk_mlx_repo": (mlx / "musetalk_mlx").exists(),
            "extract_script": (mlx / "scripts" / "extract_landmarks.py").exists(),
            "build_script": (mlx / "scripts" / "build_video.py").exists(),
            "upstream_musetalk": (upstream / "musetalk" / "utils").exists(),
            "mlx_model": (model_dir / "config.json").exists(),
            "dwpose_onnx": (mlx / "weights" / "dwpose" / "dw-ll_ucoco_384.onnx").exists(),
            "yolox_onnx": (mlx / "weights" / "dwpose" / "yolox_l.onnx").exists(),
            "face_parse": (upstream / "models" / "face-parse-bisent" / "79999_iter.pth").exists(),
            "resnet18": (upstream / "models" / "face-parse-bisent" / "resnet18-5c106cde.pth").exists(),
        }
        return {"ready": all(checks.values()), "variant": variant, "checks": checks}

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

    def _repair_missing_coords(self, coords_file: Path, log_file: Path) -> int:
        """Fill intermittent detector misses with the closest previous/next valid face box."""
        with coords_file.open("rb") as f:
            meta = pickle.load(f)
        coords = list(meta.get("coords", []))
        if not coords:
            raise EngineError("no frames/face coordinates were produced")

        valid = [i for i, box in enumerate(coords) if tuple(box) != self.PLACEHOLDER]
        if not valid:
            raise EngineError("no face was detected in the master video")

        repaired = 0
        first_valid = valid[0]
        for i in range(first_valid):
            coords[i] = coords[first_valid]
            repaired += 1

        last_box = coords[first_valid]
        for i in range(first_valid, len(coords)):
            if tuple(coords[i]) == self.PLACEHOLDER:
                coords[i] = last_box
                repaired += 1
            else:
                last_box = coords[i]

        meta["coords"] = coords
        with coords_file.open("wb") as f:
            pickle.dump(meta, f)
        if repaired:
            with log_file.open("a", encoding="utf-8") as log:
                log.write(f"\n[repair] filled {repaired} frames with neighboring face boxes\n")
        return repaired

    def render(
        self,
        video: Path,
        audio: Path,
        variant: str = "q8",
        output: Path | None = None,
        job_id: str | None = None,
    ) -> RenderResult:
        status = self.readiness(variant)
        if not status["ready"]:
            missing = [k for k, ok in status["checks"].items() if not ok]
            raise EngineError("engine is not ready; missing: " + ", ".join(missing))

        if not video.exists():
            raise EngineError(f"video not found: {video}")
        if not audio.exists():
            raise EngineError(f"audio not found: {audio}")

        job_id = job_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        work = settings.workspace_dir / job_id
        frames = work / "frames"
        work.mkdir(parents=True, exist_ok=True)
        frames.mkdir(parents=True, exist_ok=True)
        log = work / "render.log"

        normalized_video = work / "master_25fps.mp4"
        normalized_audio = work / "voice_16k.wav"
        coords = work / "coords.pkl"
        final = output or (settings.outputs_dir / job_id / "result.mp4")
        final.parent.mkdir(parents=True, exist_ok=True)

        started = time.time()

        self._run(
            [
                "ffmpeg", "-y", "-i", str(video), "-vf", f"fps={settings.target_fps}",
                "-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                str(normalized_video),
            ],
            log_file=log,
        )
        self._run(
            [
                "ffmpeg", "-y", "-i", str(audio), "-vn", "-ar", "16000", "-ac", "1",
                "-c:a", "pcm_s16le", str(normalized_audio),
            ],
            log_file=log,
        )

        mlx = settings.musetalk_mlx_dir
        self._run(
            [
                sys.executable,
                str(mlx / "scripts" / "extract_landmarks.py"),
                str(normalized_video), str(frames), str(coords),
            ],
            cwd=mlx,
            log_file=log,
        )
        self._repair_missing_coords(coords, log)
        self._run(
            [
                sys.executable,
                str(mlx / "scripts" / "build_video.py"),
                str(coords), str(normalized_audio), str(final),
                "--variant", variant,
            ],
            cwd=mlx,
            log_file=log,
        )

        elapsed = time.time() - started
        metadata = {
            "job_id": job_id,
            "video": str(video),
            "audio": str(audio),
            "variant": variant,
            "output": str(final),
            "elapsed_seconds": round(elapsed, 2),
        }
        (work / "job.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return RenderResult(job_id=job_id, output=final, workspace=work, elapsed_seconds=elapsed)
