from __future__ import annotations

import json
import pickle
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app.config import settings

from .base import EngineError, RenderResult


class MuseTalkMLXEngine:
    """Fast lip-sync engine using MuseTalk 1.5 MLX on Apple Silicon."""

    name = "musetalk"
    PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)

    def __init__(self) -> None:
        settings.ensure_runtime_dirs()

    def readiness(self, variant: str | None = None) -> dict:
        variant = variant or settings.default_musetalk_variant
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
        return {
            "engine": self.name,
            "ready": all(checks.values()),
            "variant": variant,
            "checks": checks,
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

    def _repair_missing_coords(self, coords_file: Path, log_file: Path) -> int:
        """Fill intermittent detector misses with the closest previous valid face box."""
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
        variant: str | None = None,
        output: Path | None = None,
        job_id: str | None = None,
    ) -> RenderResult:
        variant = variant or settings.default_musetalk_variant
        status = self.readiness(variant)
        if not status["ready"]:
            missing = [k for k, ok in status["checks"].items() if not ok]
            raise EngineError("MuseTalk engine is not ready; missing: " + ", ".join(missing))

        if not video.exists():
            raise EngineError(f"video not found: {video}")
        if not audio.exists():
            raise EngineError(f"audio not found: {audio}")

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

        # Check master video pre-extracted cache
        import hashlib
        stat = video.stat()
        video_hash = hashlib.md5(f"{video.resolve()}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()[:12]
        cache_dir = settings.workspace_dir / "cache" / "musetalk" / video_hash
        cache_coords = cache_dir / "coords.pkl"
        cache_frames = cache_dir / "frames"
        cache_video = cache_dir / "master_25fps.mp4"

        repaired = 0
        if cache_coords.exists() and cache_frames.exists() and cache_video.exists():
            coords = cache_coords
            if log:
                with log.open("a", encoding="utf-8") as lf:
                    lf.write(f"\n[cache hit] Reusing pre-extracted face coordinates from {cache_coords}\n")
        else:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_frames.mkdir(parents=True, exist_ok=True)
            self._run(
                [
                    "ffmpeg", "-y", "-i", str(video), "-vf", f"fps={settings.musetalk_target_fps}",
                    "-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                    str(cache_video),
                ],
                log_file=log,
            )
            mlx = settings.musetalk_mlx_dir
            extract_script = settings.root / "scripts" / "extract_landmarks.py"
            if not extract_script.exists():
                extract_script = mlx / "scripts" / "extract_landmarks.py"
            self._run(
                [
                    sys.executable,
                    str(extract_script),
                    str(cache_video), str(cache_frames), str(cache_coords),
                ],
                cwd=mlx,
                log_file=log,
            )
            self._repair_missing_coords(cache_coords, log)
            coords = cache_coords

        mlx = settings.musetalk_mlx_dir
        final_abs = Path(final).resolve()
        final_abs.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                sys.executable,
                str(mlx / "scripts" / "build_video.py"),
                str(Path(coords).resolve()),
                str(Path(normalized_audio).resolve()),
                str(final_abs),
                "--variant", variant,
            ],
            cwd=mlx,
            log_file=log,
        )

        elapsed = time.time() - started
        metadata = {
            "job_id": job_id,
            "engine": self.name,
            "video": str(video),
            "audio": str(audio),
            "variant": variant,
            "output": str(final),
            "repaired_face_boxes": repaired,
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
