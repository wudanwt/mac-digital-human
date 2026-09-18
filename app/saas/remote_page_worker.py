from __future__ import annotations

import hashlib
import fcntl
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import httpx
import psutil

from ..composer import CourseComposer, media_duration
from ..config import settings as app_settings
from ..engines import MuseTalkMLXEngine
from .render_core import PageRenderPlan, RenderWorkspace, execute_page
from .settings import saas_settings
from .tts_pipeline import build_course_tts, normalize_external_audio, synthesize_course_audio
from .worker_entry import (
    CourseMatteContext,
    ContextualMatteMuseTalkEngine,
    MatteAwareCourseComposer,
    _CONTEXT,
)

log = logging.getLogger("digital-human.saas.remote-page-worker")


@contextmanager
def worker_instance_lock(cache_dir: Path):
    """Keep one page-worker process per cache/model runtime on a Mac."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / ".remote-page-worker.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another remote page worker is already running for {cache_dir}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


@dataclass(frozen=True)
class RemoteWorkerConfig:
    api_base: str
    token: str
    name: str
    code_version: str
    model_version: str
    render_contract_version: str
    cache_dir: Path
    cache_limit_bytes: int
    min_disk_free_bytes: int
    transfer_slots: int
    upload_chunk_bytes: int
    request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "RemoteWorkerConfig":
        api_base = os.getenv(
            "REMOTE_WORKER_API_BASE",
            "http://127.0.0.1:8918/api/saas/internal/render",
        ).rstrip("/")
        token = os.getenv("REMOTE_WORKER_TOKEN", "").strip()
        if not token:
            raise RuntimeError("REMOTE_WORKER_TOKEN is required")
        return cls(
            api_base=api_base,
            token=token,
            name=os.getenv("REMOTE_WORKER_NAME", socket.gethostname()).strip() or socket.gethostname(),
            code_version=os.getenv("REMOTE_WORKER_CODE_VERSION", "0.5.0").strip(),
            model_version=os.getenv("REMOTE_WORKER_MODEL_VERSION", "musetalk-mlx").strip(),
            render_contract_version=os.getenv(
                "REMOTE_WORKER_RENDER_CONTRACT_VERSION",
                saas_settings.render_contract_version,
            ).strip(),
            cache_dir=Path(
                os.getenv(
                    "REMOTE_WORKER_CACHE_DIR",
                    str(app_settings.workspace_dir / "remote-worker-cache"),
                )
            ),
            cache_limit_bytes=max(
                1,
                int(os.getenv("REMOTE_WORKER_CACHE_GB", str(saas_settings.distributed_cache_gb))),
            ) * 1024**3,
            min_disk_free_bytes=max(
                1,
                int(
                    os.getenv(
                        "REMOTE_WORKER_MIN_DISK_FREE_GB",
                        str(saas_settings.distributed_min_disk_free_gb),
                    )
                ),
            ) * 1024**3,
            transfer_slots=max(
                1,
                min(
                    2,
                    int(
                        os.getenv(
                            "REMOTE_WORKER_TRANSFER_SLOTS",
                            str(saas_settings.distributed_transfer_slots),
                        )
                    ),
                ),
            ),
            upload_chunk_bytes=max(
                1,
                int(
                    os.getenv(
                        "REMOTE_WORKER_UPLOAD_CHUNK_MB",
                        str(saas_settings.distributed_upload_chunk_mb),
                    )
                ) * 1024**2,
            ),
            request_timeout_seconds=float(os.getenv("REMOTE_WORKER_HTTP_TIMEOUT_SECONDS", "120")),
        )


class LeaseLost(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed: {path}")
    data = json.loads(proc.stdout or "{}")
    video = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
    audio = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), {})
    frame_raw = str(video.get("nb_frames") or "")
    sample_rate_raw = str(audio.get("sample_rate") or "")
    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": video.get("avg_frame_rate") or video.get("r_frame_rate") or "",
        "pix_fmt": video.get("pix_fmt") or "",
        "video_codec": video.get("codec_name") or "",
        "frame_count": int(frame_raw) if frame_raw.isdigit() else 0,
        "audio_codec": audio.get("codec_name") or "",
        "audio_sample_rate": int(sample_rate_raw) if sample_rate_raw.isdigit() else 0,
        "audio_channels": int(audio.get("channels") or 0),
        "duration": float((data.get("format") or {}).get("duration") or 0.0),
    }


class RemoteApi:
    """Authenticated control-plane client used by a compute-only Mac worker."""

    def __init__(self, config: RemoteWorkerConfig) -> None:
        self.config = config
        parsed = urlsplit(config.api_base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("REMOTE_WORKER_API_BASE must be an absolute http(s) URL")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        # A base URL is intentional: task manifests use same-origin relative
        # download URLs so the center never has to expose its object-store URL.
        self.client = httpx.Client(
            base_url=self.origin,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=httpx.Timeout(config.request_timeout_seconds, connect=15.0),
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def _url(self, suffix: str) -> str:
        return f"{self.config.api_base}/{suffix.lstrip('/')}"

    def _resource_url(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"{self.origin}/{value.lstrip('/')}"

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else payload
        except Exception:
            detail = response.text
        raise RuntimeError(f"center API {response.status_code}: {detail}")

    def register(self) -> dict[str, Any]:
        response = self.client.post(
            self._url("register"),
            json={
                "name": self.config.name,
                "host": socket.gethostname(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "slots_total": 1,
                "capabilities": [
                    "musetalk",
                    "speech-preview",
                    "transparent-avatar-compose",
                ],
                "versions": {"python": platform.python_version()},
                "code_version": self.config.code_version,
                "model_version": self.config.model_version,
                "render_contract_version": self.config.render_contract_version,
            },
        )
        self._raise(response)
        return response.json()

    def heartbeat(
        self,
        *,
        current_task_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        usage = shutil.disk_usage(self.config.cache_dir)
        memory = psutil.virtual_memory()
        response = self.client.post(
            self._url("heartbeat"),
            json={
                "current_task_id": current_task_id,
                "disk_free_bytes": usage.free,
                "memory_available_mb": int(memory.available / 1024**2),
                "last_error": error,
            },
        )
        self._raise(response)
        return response.json()

    def claim(self) -> dict[str, Any] | None:
        response = self.client.post(self._url("tasks/claim"))
        self._raise(response)
        payload = response.json()
        return payload.get("task") if isinstance(payload, dict) else None

    def renew(self, task: dict[str, Any]) -> str:
        response = self.client.post(
            self._url(f"tasks/{task['id']}/renew"),
            json={
                "attempt_id": task["attempt_id"],
                "lease_token": task["lease_token"],
            },
        )
        self._raise(response)
        return str(response.json()["lease_expires_at"])

    def progress(
        self,
        task: dict[str, Any],
        progress: int,
        stage: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        response = self.client.post(
            self._url(f"tasks/{task['id']}/progress"),
            json={
                "attempt_id": task["attempt_id"],
                "lease_token": task["lease_token"],
                "progress": progress,
                "stage": stage,
                "metrics": metrics or {},
            },
        )
        self._raise(response)

    def fail(
        self,
        task: dict[str, Any],
        error: str,
        retryable: bool,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        response = self.client.post(
            self._url(f"tasks/{task['id']}/fail"),
            json={
                "attempt_id": task["attempt_id"],
                "lease_token": task["lease_token"],
                "error": error[:8000],
                "retryable": retryable,
                "metrics": metrics or {},
            },
        )
        self._raise(response)

    def complete(
        self,
        task: dict[str, Any],
        *,
        metrics: dict[str, Any],
        media: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.post(
            self._url(f"tasks/{task['id']}/complete"),
            json={
                "attempt_id": task["attempt_id"],
                "lease_token": task["lease_token"],
                "metrics": metrics,
                "media": media,
            },
        )
        self._raise(response)
        return response.json()

    @staticmethod
    def _lease_headers(task: dict[str, Any]) -> dict[str, str]:
        return {
            "X-Attempt-Id": task["attempt_id"],
            "X-Lease-Token": task["lease_token"],
        }

    def download(
        self,
        task: dict[str, Any],
        descriptor: dict[str, Any],
        destination: Path,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        existing = part.stat().st_size if part.exists() else 0
        headers = self._lease_headers(task)
        if existing:
            headers["Range"] = f"bytes={existing}-"
        resource_url = self._resource_url(str(descriptor["url"]))
        with self.client.stream("GET", resource_url, headers=headers) as response:
            if existing and response.status_code == 200:
                part.unlink(missing_ok=True)
                existing = 0
            if response.status_code not in {200, 206}:
                self._raise(response)
            mode = "ab" if existing and response.status_code == 206 else "wb"
            with part.open(mode) as fh:
                for chunk in response.iter_bytes(1024 * 1024):
                    fh.write(chunk)

        expected_size = int(descriptor.get("size_bytes") or 0)
        if expected_size and part.stat().st_size != expected_size:
            raise RuntimeError(f"download size mismatch for {descriptor['id']}")
        digest = _sha256(part)
        expected_hash = str(descriptor.get("sha256") or "").lower()
        if expected_hash and digest != expected_hash:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"download hash mismatch for {descriptor['id']}")
        part.replace(destination)
        os.utime(destination, None)
        return destination

    def upload(
        self,
        task: dict[str, Any],
        *,
        kind: str,
        source: Path,
    ) -> dict[str, Any]:
        digest = _sha256(source)
        headers = self._lease_headers(task)
        status_url = self._url(f"tasks/{task['id']}/artifacts/{kind}/upload")
        response = self.client.get(status_url, headers=headers)
        self._raise(response)
        status = response.json()
        if status.get("completed"):
            if status.get("sha256") and status["sha256"] != digest:
                raise RuntimeError(f"center already has a different {kind} artifact")
            return status

        offset = int(status.get("received_bytes") or 0)
        total = source.stat().st_size
        if offset > total:
            raise RuntimeError(f"center upload offset exceeds local file for {kind}")
        upload_url = self._url(f"tasks/{task['id']}/artifacts/{kind}")
        payload: dict[str, Any] = {"completed": False, "received_bytes": offset}
        with source.open("rb") as fh:
            fh.seek(offset)
            while offset < total:
                chunk = fh.read(min(self.config.upload_chunk_bytes, total - offset))
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                chunk_headers = {
                    **headers,
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                }
                if end + 1 == total:
                    chunk_headers["X-Content-SHA256"] = digest
                response = self.client.put(
                    upload_url,
                    headers=chunk_headers,
                    content=chunk,
                )
                self._raise(response)
                payload = response.json()
                offset = int(payload.get("received_bytes") or end + 1)
        if offset != total:
            raise RuntimeError(f"incomplete artifact upload for {kind}: {offset}/{total}")
        return payload


class ContentCache:
    def __init__(self, config: RemoteWorkerConfig, api: RemoteApi) -> None:
        self.config = config
        self.api = api
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._active: set[Path] = set()

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _path(self, descriptor: dict[str, Any]) -> Path:
        digest = str(descriptor.get("sha256") or descriptor["id"])
        name = str(descriptor.get("name") or descriptor.get("kind") or "asset.bin")
        content_type = str(descriptor.get("content_type") or "")
        suffix = Path(name).suffix
        if not suffix:
            suffix = {
                "video/mp4": ".mp4",
                "audio/wav": ".wav",
                "image/png": ".png",
            }.get(content_type, ".bin")
        return self.config.cache_dir / f"{digest}{suffix}"

    def acquire(self, task: dict[str, Any], descriptor: dict[str, Any]) -> Path:
        path = self._path(descriptor)
        key = str(descriptor.get("sha256") or descriptor["id"])
        with self._lock(key):
            expected_hash = str(descriptor.get("sha256") or "").lower()
            expected_size = int(descriptor.get("size_bytes") or 0)
            valid = path.exists()
            if valid and expected_size:
                valid = path.stat().st_size == expected_size
            if valid and expected_hash:
                valid = _sha256(path) == expected_hash
            if not valid:
                path.unlink(missing_ok=True)
                self.api.download(task, descriptor, path)
            os.utime(path, None)
        with self._guard:
            self._active.add(path)
        return path

    def release_all(self) -> None:
        with self._guard:
            self._active.clear()
        self.cleanup()

    def cleanup(self) -> None:
        files = [
            path
            for path in self.config.cache_dir.iterdir()
            if path.is_file() and not path.name.endswith(".part")
        ]
        total = sum(path.stat().st_size for path in files)
        if total <= self.config.cache_limit_bytes:
            return
        with self._guard:
            active = set(self._active)
        for path in sorted(files, key=lambda item: item.stat().st_mtime):
            if path in active:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
            if total <= self.config.cache_limit_bytes:
                break


class LeaseKeeper:
    def __init__(self, api: RemoteApi, task: dict[str, Any], interval: int) -> None:
        self.api = api
        self.task = task
        self.interval = max(3, interval)
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.thread = threading.Thread(
            target=self._loop,
            name=f"lease-{task['id']}",
            daemon=True,
        )

    def _loop(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                self.api.renew(self.task)
            except Exception as exc:  # noqa: BLE001
                log.error("lease renew failed task=%s error=%s", self.task["id"], exc)
                self.lost_event.set()
                return

    def __enter__(self) -> "LeaseKeeper":
        self.thread.start()
        return self

    def checkpoint(self) -> None:
        if self.lost_event.is_set():
            raise LeaseLost("worker lost the active task lease")

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)


class RemotePageWorker:
    def __init__(self, config: RemoteWorkerConfig) -> None:
        self.config = config
        self.api = RemoteApi(config)
        self.cache = ContentCache(config, self.api)
        self._current_task_id: str | None = None
        self._last_error: str | None = None
        self._stop = threading.Event()
        self.avatar_engine = ContextualMatteMuseTalkEngine(MuseTalkMLXEngine())
        self.composer = MatteAwareCourseComposer(CourseComposer().config)

    def register(self) -> None:
        payload = self.api.register()
        log.info("Remote worker registered: %s", payload.get("worker", {}).get("id"))

    def start_heartbeat(self) -> threading.Thread:
        def loop() -> None:
            while not self._stop.wait(max(3, saas_settings.distributed_renew_seconds)):
                try:
                    self.api.heartbeat(
                        current_task_id=self._current_task_id,
                        error=self._last_error,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("worker heartbeat failed: %s", exc)

        thread = threading.Thread(
            target=loop,
            name="remote-worker-heartbeat",
            daemon=True,
        )
        thread.start()
        return thread

    def _disk_ready(self) -> bool:
        return shutil.disk_usage(self.config.cache_dir).free >= self.config.min_disk_free_bytes

    def _download_inputs(self, task: dict[str, Any]) -> dict[str, Path]:
        descriptors = [
            *(task.get("assets") or []),
            *(task.get("prepared_artifacts") or []),
        ]
        output: dict[str, Path] = {}
        with ThreadPoolExecutor(
            max_workers=self.config.transfer_slots,
            thread_name_prefix="asset-transfer",
        ) as executor:
            future_map = {
                executor.submit(self.cache.acquire, task, item): item
                for item in descriptors
            }
            for future in as_completed(future_map):
                item = future_map[future]
                output[str(item["id"])] = future.result()
        return output

    @staticmethod
    def _voice_proxy(payload: dict[str, Any] | None):
        if not payload:
            return None
        return SimpleNamespace(
            id=payload.get("id") or "frozen-voice",
            provider=payload.get("provider") or "cosyvoice",
            reference_asset_id=payload.get("reference_asset_id"),
            transcript=payload.get("transcript") or "",
            settings_json=json.dumps(payload.get("settings") or {}, ensure_ascii=False),
            updated_at=None,
        )

    def _execute(
        self,
        task: dict[str, Any],
        lease: LeaseKeeper,
    ) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
        payload = dict(task.get("payload") or {})
        index = int(payload.get("index") or task["slide_index"])
        work = RenderWorkspace.create(
            app_settings.workspace_dir / "remote-page-worker" / task["attempt_id"]
        )
        files = self._download_inputs(task)
        lease.checkpoint()
        self.api.progress(task, 10, "assets_ready", {"asset_count": len(files)})

        slide_artifact_id = str(payload.get("slide_artifact_id") or "")
        if not slide_artifact_id or slide_artifact_id not in files:
            raise ValueError("prepared slide artifact is missing from the task manifest")
        slide_target = work.slide_dir / f"slide-{index}.png"
        shutil.copy2(files[slide_artifact_id], slide_target)

        master_id = str(payload.get("master_video_asset_id") or "")
        if not master_id or master_id not in files:
            raise ValueError("master video asset is missing from the task manifest")
        master_path = files[master_id]
        alpha_id = str(payload.get("alpha_asset_id") or "")
        alpha_path = files.get(alpha_id) if alpha_id else None

        background_id = str(payload.get("background_asset_id") or "")
        override = dict(payload.get("override") or {})
        if background_id and background_id in files and override.get("custom_bg"):
            target = (
                app_settings.workspace_dir
                / "backgrounds"
                / Path(str(override["custom_bg"])).name
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(files[background_id], target)

        narration = str(payload.get("narration") or "").strip()
        plan = PageRenderPlan(
            index=index,
            title=str(payload.get("title") or ""),
            narration=narration,
            layout=str(payload.get("layout") or "pip"),
            override=override,
            slide=SimpleNamespace(index=index),
        )
        course_settings = dict(payload.get("course_settings") or {})
        voice = self._voice_proxy(payload.get("voice"))
        ref_id = str(payload.get("reference_audio_asset_id") or "")
        ref_path = files.get(ref_id) if ref_id else None
        audio_id = str(payload.get("audio_asset_id") or "")
        prepared_audio: Path | None = None
        prepared_audio_source: str | None = None
        tts_runtime = None

        if audio_id:
            if audio_id not in files:
                raise ValueError("fixed page audio is missing from the task manifest")
            prepared_audio = normalize_external_audio(
                files[audio_id],
                work.audio_dir / f"{index:03d}.wav",
            )
            prepared_audio_source = str(payload.get("audio_source") or "fixed")
        else:
            if voice is None:
                raise ValueError("page requires TTS but frozen voice configuration is missing")
            tts_runtime = build_course_tts(
                voice,
                ref_audio=ref_path,
                course_settings=course_settings,
                base=work.root,
            )

        def make_audio(page_plan: PageRenderPlan) -> Path:
            nonlocal tts_runtime
            if tts_runtime is None:
                raise RuntimeError("TTS runtime is not available")
            runtime = tts_runtime
            try:
                return synthesize_course_audio(
                    runtime,
                    page_plan.narration,
                    work.audio_dir / f"{page_plan.index:03d}.wav",
                )
            finally:
                # A 16GB mini must not retain the TTS model while MuseTalk is
                # rendering the same page. TTS and lip-sync remain strictly
                # serial and quality parameters are unchanged.
                try:
                    runtime.provider.release()
                finally:
                    tts_runtime = None

        context = CourseMatteContext()
        avatar_mode = str(payload.get("avatar_mode") or "original").lower()
        context.modes_by_slide[index] = avatar_mode
        if avatar_mode in {"transparent", "white"}:
            if alpha_path is None:
                raise ValueError("transparent/white page requires a prepared alpha asset")
            context.alpha_source = alpha_path

        stage_metrics: dict[str, Any] = {}

        def on_stage(stage: str, detail: dict[str, Any]) -> None:
            lease.checkpoint()
            mapping = {
                "audio_start": 20,
                "audio_done": 35,
                "video_start": 40,
                "video_done": 75,
                "video_skipped": 75,
                "compose_start": 80,
                "compose_done": 90,
            }
            stage_metrics[stage] = detail
            self.api.progress(task, mapping.get(stage, 50), stage, detail)

        _CONTEXT.value = context
        try:
            result = execute_page(
                plan=plan,
                workspace=work,
                prepare_audio=make_audio,
                avatar_engine=self.avatar_engine,
                composer=self.composer,
                master_path=master_path,
                master_cache_key=f"remote:{master_id}:{_sha256(master_path)}",
                job_id=task["parent_job_id"],
                settings_payload=course_settings,
                prepared_audio=prepared_audio,
                prepared_audio_source=prepared_audio_source,
                on_stage=on_stage,
            )
        finally:
            _CONTEXT.value = None
            if tts_runtime is not None:
                try:
                    tts_runtime.provider.release()
                except Exception:
                    pass
                tts_runtime = None

        lease.checkpoint()
        probe = _ffprobe(result.segment_path)
        audio_seconds = media_duration(result.audio_path)
        media = {
            "video_seconds": probe["duration"] or result.audio_seconds,
            "audio_seconds": audio_seconds,
            "frame_count": probe["frame_count"],
            "encoding": {
                "width": probe["width"],
                "height": probe["height"],
                "fps": probe["fps"],
                "pix_fmt": probe["pix_fmt"],
                "video_codec": probe["video_codec"],
                "audio_codec": probe["audio_codec"],
                "audio_sample_rate": probe["audio_sample_rate"],
                "audio_channels": probe["audio_channels"],
            },
        }
        metrics = {
            "tts_elapsed_seconds": result.tts_elapsed_seconds,
            "render_seconds": result.render_seconds,
            "audio_source": result.audio_source,
            "stages": stage_metrics,
        }
        return result.segment_path, result.audio_path, media, metrics

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        terminal_markers = (
            "out of memory",
            "memoryerror",
            "hash mismatch",
            "config",
            "contract mismatch",
            "requires a prepared alpha",
            "missing from the task manifest",
            "provider is not ready",
        )
        return not isinstance(exc, (MemoryError, ValueError)) and not any(
            marker in message for marker in terminal_markers
        )

    def process_task(self, task: dict[str, Any]) -> None:
        self._current_task_id = task["id"]
        self._last_error = None
        started = time.time()
        try:
            with LeaseKeeper(
                self.api,
                task,
                saas_settings.distributed_renew_seconds,
            ) as lease:
                video, audio, media, metrics = self._execute(task, lease)
                lease.checkpoint()
                self.api.progress(task, 92, "uploading", metrics)
                self.api.upload(task, kind="page_audio", source=audio)
                lease.checkpoint()
                self.api.upload(task, kind="page_video", source=video)
                lease.checkpoint()
                metrics["worker_elapsed_seconds"] = round(time.time() - started, 3)
                self.api.complete(task, metrics=metrics, media=media)
        except LeaseLost:
            # The center has already recovered/reassigned this attempt. A late
            # worker must never report or publish over the newer attempt.
            log.warning("Lease lost for task %s; abandoning local result", task["id"])
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            log.exception("Remote page task failed task=%s", task["id"])
            try:
                self.api.fail(
                    task,
                    error=str(exc),
                    retryable=self._retryable(exc),
                    metrics={
                        "worker_elapsed_seconds": round(time.time() - started, 3)
                    },
                )
            except Exception as report_exc:  # noqa: BLE001
                # If the center cannot be reached, the lease reaper is the source
                # of truth and will recover the page after expiry.
                log.warning("Unable to report task failure: %s", report_exc)
        finally:
            self._current_task_id = None
            self.cache.release_all()

    def run_forever(self) -> None:
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self.register()
        heartbeat = self.start_heartbeat()
        try:
            while not self._stop.is_set():
                if not self._disk_ready():
                    self._last_error = "disk free below configured safety threshold"
                    try:
                        self.api.heartbeat(error=self._last_error)
                    except Exception:
                        pass
                    self.cache.cleanup()
                    time.sleep(5)
                    continue
                self._last_error = None
                try:
                    task = self.api.claim()
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    log.warning("Task claim failed: %s", exc)
                    time.sleep(3)
                    continue
                if task is None:
                    time.sleep(1)
                    continue
                self.process_task(task)
        finally:
            self._stop.set()
            heartbeat.join(timeout=2)
            self.api.close()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    config = RemoteWorkerConfig.from_env()
    with worker_instance_lock(config.cache_dir):
        RemotePageWorker(config).run_forever()


if __name__ == "__main__":
    main()
