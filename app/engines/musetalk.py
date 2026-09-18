from __future__ import annotations

import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from app.config import settings

from .base import EngineError, RenderResult


class MuseTalkMLXEngine:
    """Fast lip-sync engine using MuseTalk 1.5 MLX on Apple Silicon."""

    name = "musetalk"
    PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)
    CACHE_VERSION = "master-v2"

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
            "resident_runtime": os.getenv("MUSETALK_RESIDENT_RUNTIME", "1").strip().lower() not in {"0", "false", "no", "off"},
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

        if repaired:
            meta["coords"] = coords
            with coords_file.open("wb") as f:
                pickle.dump(meta, f)
            with log_file.open("a", encoding="utf-8") as log:
                log.write(f"\n[repair] filled {repaired} frames with neighboring face boxes\n")
        return repaired

    @classmethod
    def _landmark_cache_complete(cls, coords_file: Path, frames_dir: Path) -> bool:
        """Return true only when landmark extraction produced a complete, usable cache.

        CoreML/ONNX Runtime can abort during interpreter teardown on macOS even
        after the extractor has flushed a valid ``coords.pkl``.  Validating the
        artifact lets the render continue in that specific case without hiding
        genuine extraction failures or accepting a partial cache.
        """
        if not coords_file.is_file() or not frames_dir.is_dir():
            return False
        try:
            with coords_file.open("rb") as f:
                meta = pickle.load(f)
            coords = list(meta.get("coords", []))
            declared = int(meta.get("n", len(coords)))
            frame_count = sum(1 for _ in frames_dir.glob("*.png"))
            paths = [Path(path) for path in meta.get("frames", [])]
        except (OSError, ValueError, TypeError, pickle.PickleError):
            return False
        if not coords or declared != len(coords) or frame_count != len(coords) or len(paths) != len(coords):
            return False
        if len({path.name for path in paths}) != len(paths):
            return False
        if any(path.parent.resolve() != frames_dir.resolve() or not path.is_file() or path.stat().st_size == 0 for path in paths):
            return False
        return any(tuple(box) != cls.PLACEHOLDER for box in coords)

    @staticmethod
    @contextmanager
    def _cache_lock(cache_dir: Path):
        import fcntl

        cache_dir.mkdir(parents=True, exist_ok=True)
        with (cache_dir / ".prepare.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @classmethod
    def _cache_digest(cls, video: Path, master_cache_key: str | None = None) -> str:
        if master_cache_key is None:
            digest = sha256()
            with video.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            identity = "file:" + digest.hexdigest()
        else:
            identity = "asset:" + master_cache_key
        key = f"{cls.CACHE_VERSION}:{settings.musetalk_target_fps}:{identity}"
        return sha256(key.encode("utf-8")).hexdigest()[:24]

    def _prepare_master_cache(self, video: Path, cache_dir: Path, log: Path) -> tuple[Path, int, dict[str, object]]:
        cache_coords = cache_dir / "coords.pkl"
        cache_frames = cache_dir / "frames"
        cache_video = cache_dir / "master_25fps.mp4"
        metrics: dict[str, object] = {"landmark_cache": "hit", "normalize_seconds": 0.0, "landmarks_seconds": 0.0}
        with self._cache_lock(cache_dir):
            if not (cache_video.is_file() and cache_video.stat().st_size > 0
                    and self._landmark_cache_complete(cache_coords, cache_frames)):
                metrics["landmark_cache"] = "built"
                with tempfile.TemporaryDirectory(prefix=".build-", dir=cache_dir) as staging:
                    stage = Path(staging)
                    stage_video = stage / "master_25fps.mp4"
                    stage_frames = stage / "frames"
                    stage_coords = stage / "coords.pkl"
                    stage_frames.mkdir()
                    started = time.perf_counter()
                    self._run(
                        [
                            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                            "-i", str(video), "-vf", f"fps={settings.musetalk_target_fps}",
                            "-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                            str(stage_video),
                        ],
                        log_file=log,
                    )
                    metrics["normalize_seconds"] = round(time.perf_counter() - started, 2)
                    mlx = settings.musetalk_mlx_dir
                    extract_script = settings.root / "scripts" / "extract_landmarks.py"
                    if not extract_script.exists():
                        extract_script = mlx / "scripts" / "extract_landmarks.py"
                    started = time.perf_counter()
                    try:
                        self._run(
                            [sys.executable, str(extract_script), str(stage_video), str(stage_frames), str(stage_coords)],
                            cwd=mlx,
                            log_file=log,
                        )
                    except EngineError:
                        if not self._landmark_cache_complete(stage_coords, stage_frames):
                            raise
                        with log.open("a", encoding="utf-8") as output:
                            output.write("\n[landmark extractor teardown warning] Complete cache validated.\n")
                    metrics["landmarks_seconds"] = round(time.perf_counter() - started, 2)
                    if not self._landmark_cache_complete(stage_coords, stage_frames):
                        raise EngineError("landmark extractor produced an incomplete cache")
                    with stage_coords.open("rb") as source:
                        meta = pickle.load(source)
                    meta["frames"] = [str(cache_frames / Path(path).name) for path in meta["frames"]]
                    with stage_coords.open("wb") as target:
                        pickle.dump(meta, target, protocol=pickle.HIGHEST_PROTOCOL)
                    if cache_frames.exists():
                        shutil.rmtree(cache_frames)
                    os.replace(stage_frames, cache_frames)
                    os.replace(stage_video, cache_video)
                    os.replace(stage_coords, cache_coords)
                    if not self._landmark_cache_complete(cache_coords, cache_frames):
                        raise EngineError("installed landmark cache is incomplete")
            else:
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"\n[cache hit] Reusing pre-extracted face coordinates from {cache_coords}\n")
            repaired = self._repair_missing_coords(cache_coords, log)
        return cache_coords, repaired, metrics

    @staticmethod
    def _resident_enabled() -> bool:
        return os.getenv("MUSETALK_RESIDENT_RUNTIME", "1").strip().lower() not in {"0", "false", "no", "off"}

    def render(
        self,
        video: Path,
        audio: Path,
        variant: str | None = None,
        output: Path | None = None,
        job_id: str | None = None,
        master_cache_key: str | None = None,
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
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-i", str(audio), "-vn", "-ar", "16000", "-ac", "1",
                "-c:a", "pcm_s16le", str(normalized_audio),
            ],
            log_file=log,
        )

        video_hash = self._cache_digest(video, master_cache_key)
        cache_dir = settings.workspace_dir / "cache" / "musetalk" / video_hash
        coords, repaired, cache_metrics = self._prepare_master_cache(video, cache_dir, log)

        runtime_metadata: dict[str, object] = {"resident": False}
        resident_error: str | None = None
        if self._resident_enabled():
            try:
                from .musetalk_runtime import get_resident_runtime

                runtime = get_resident_runtime(variant)
                material_started = time.perf_counter()
                with self._cache_lock(cache_dir):
                    material = runtime.prepare_master(Path(coords).resolve(), cache_dir)
                    material_cache = runtime.last_material_cache_status
                cache_metrics["material_prepare_seconds"] = round(time.perf_counter() - material_started, 2)
                cache_metrics["material_cache"] = material_cache
                with log.open("a", encoding="utf-8") as lf:
                    lf.write(
                        f"\n[cache] landmarks={cache_metrics['landmark_cache']} "
                        f"normalize={cache_metrics['normalize_seconds']}s "
                        f"landmarks_elapsed={cache_metrics['landmarks_seconds']}s "
                        f"material={material_cache} prepare={cache_metrics['material_prepare_seconds']}s\n"
                    )
                runtime_metadata = runtime.render(
                    coords_file=Path(coords).resolve(),
                    audio=Path(normalized_audio).resolve(),
                    output=Path(final).resolve(),
                    cache_dir=cache_dir,
                    log_file=log,
                    prepared_material=material,
                )
                runtime_metadata.update(cache_metrics)
            except Exception as exc:  # noqa: BLE001 - reliability fallback is deliberate
                resident_error = str(exc)
                with log.open("a", encoding="utf-8") as lf:
                    lf.write(f"\n[resident-runtime fallback] {resident_error}\n")

        # Safe fallback to the upstream per-slide helper.  Keeping this path makes
        # the optimization reversible on any Mac where a third-party runtime
        # dependency behaves differently.
        if not Path(final).exists():
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
            "cache": cache_metrics,
            "resident_runtime": runtime_metadata,
            "resident_fallback_error": resident_error,
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
