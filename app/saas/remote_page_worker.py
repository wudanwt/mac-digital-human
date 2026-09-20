from __future__ import annotations

import hashlib
import fcntl
import ipaddress
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
from ..engines import create_musetalk_engine, normalize_musetalk_backend
from ..video_encoding import video_encoder_info
from .avatar_matting_engine import PortraitMattingEngine
from .media_cues import media_cue_asset_ids
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


def worker_lock_path(cache_dir: Path) -> Path:
    """Place the process lock outside the evictable content cache."""
    resolved = cache_dir.expanduser().resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    return resolved.parent / ".remote-worker-locks" / f"{digest}.lock"


@contextmanager
def worker_instance_lock(cache_dir: Path):
    """Keep one page-worker process per cache/model runtime on a compute node."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = worker_lock_path(cache_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
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
    render_backend: str = "mlx"

    @classmethod
    def from_env(cls) -> "RemoteWorkerConfig":
        api_base_env = os.getenv("REMOTE_WORKER_API_BASE", "").strip()
        render_backend = normalize_musetalk_backend(os.getenv("REMOTE_WORKER_RENDER_BACKEND", "mlx"))
        token = os.getenv("REMOTE_WORKER_TOKEN", "").strip()
        agent_runtime = None
        if not token:
            try:
                from .remote_worker_agent import load_agent_runtime

                agent_runtime = load_agent_runtime()
            except Exception as exc:  # noqa: BLE001
                if platform.system() != "Darwin":
                    raise RuntimeError(
                        "REMOTE_WORKER_TOKEN is required on non-macOS remote workers"
                    ) from exc
                raise RuntimeError(
                    "REMOTE_WORKER_TOKEN is not set and no enrolled macOS Keychain credential is available"
                ) from exc
            token = agent_runtime.token
        api_base = (
            api_base_env
            or (agent_runtime.api_base if agent_runtime is not None else "")
            or "http://127.0.0.1:8918/api/saas/internal/render"
        ).rstrip("/")
        env_name = os.getenv("REMOTE_WORKER_NAME", "").strip()
        default_name = (
            agent_runtime.name
            if agent_runtime is not None and agent_runtime.name
            else socket.gethostname()
        )
        return cls(
            api_base=api_base,
            token=token,
            name=env_name or default_name,
            code_version=os.getenv("REMOTE_WORKER_CODE_VERSION", "0.5.0").strip(),
            model_version=os.getenv(
                "REMOTE_WORKER_MODEL_VERSION",
                "musetalk-cuda" if render_backend == "cuda" else "musetalk-mlx",
            ).strip(),
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
            render_backend=render_backend,
        )


class RemoteApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LeaseLost(RuntimeError):
    pass


def _is_private_or_local_host(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


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
        allow_insecure = os.getenv("REMOTE_WORKER_ALLOW_INSECURE_HTTP", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if parsed.scheme == "http" and not _is_private_or_local_host(parsed.hostname) and not allow_insecure:
            raise RuntimeError(
                "public remote Center endpoints must use HTTPS; "
                "set REMOTE_WORKER_ALLOW_INSECURE_HTTP=1 only for a trusted private network"
            )
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        # Control-plane credentials must never be sent to object storage.
        # Keep authenticated Center traffic and unauthenticated signed-URL
        # transfers on separate clients.
        timeout = httpx.Timeout(config.request_timeout_seconds, connect=15.0)
        self.control_client = httpx.Client(
            base_url=self.origin,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=timeout,
            trust_env=False,
        )
        self.transfer_client = httpx.Client(
            timeout=timeout,
            trust_env=False,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.control_client.close()
        self.transfer_client.close()

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
        raise RemoteApiError(f"center API {response.status_code}: {detail}", status_code=response.status_code)

    def register(self) -> dict[str, Any]:
        encoder = video_encoder_info() if self.config.render_backend == "cuda" else None
        capabilities = [
            "musetalk",
            "speech-preview",
            "portrait-matting",
            "transparent-avatar-compose",
            "script-media-cues",
            f"backend:{self.config.render_backend}",
            "accelerator:nvidia-cuda" if self.config.render_backend == "cuda" else "accelerator:apple-mlx",
        ]
        if encoder is not None:
            capabilities.append(f"video-encoder:{encoder['selected']}")
            resident_enabled = os.getenv("MUSETALK_CUDA_RESIDENT", "1").strip().lower() not in {
                "0", "false", "no", "off"
            }
            capabilities.append(
                "musetalk-runtime:resident-v3" if resident_enabled else "musetalk-runtime:streaming-v2"
            )
        response = self.control_client.post(
            self._url("register"),
            json={
                "name": self.config.name,
                "host": socket.gethostname(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "slots_total": 1,
                "capabilities": capabilities,
                "versions": {
                    "python": platform.python_version(),
                    "musetalk_backend": self.config.render_backend,
                    **(
                        {
                            "video_encoder": str(encoder["selected"]),
                            "musetalk_runtime": (
                                "resident-v3"
                                if os.getenv("MUSETALK_CUDA_RESIDENT", "1").strip().lower()
                                not in {"0", "false", "no", "off"}
                                else "streaming-v2"
                            ),
                        }
                        if encoder is not None
                        else {}
                    ),
                },
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
        response = self.control_client.post(
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
        response = self.control_client.post(self._url("tasks/claim"))
        self._raise(response)
        payload = response.json()
        return payload.get("task") if isinstance(payload, dict) else None

    def claim_auxiliary(self) -> dict[str, Any] | None:
        response = self.control_client.post(self._url("aux/claim"))
        self._raise(response)
        payload = response.json()
        return payload.get("task") if isinstance(payload, dict) else None

    def renew_auxiliary(self, task: dict[str, Any]) -> str:
        response = self.control_client.post(
            self._url(f"aux/{task['id']}/renew"),
            json={"lease_token": task["lease_token"]},
        )
        self._raise(response)
        return str(response.json()["lease_expires_at"])

    def progress_auxiliary(self, task: dict[str, Any], progress: int, stage: str) -> None:
        response = self.control_client.post(
            self._url(f"aux/{task['id']}/progress"),
            json={"lease_token": task["lease_token"], "progress": progress, "stage": stage[:80]},
        )
        self._raise(response)

    def upload_auxiliary(self, task: dict[str, Any], kind: str, source: Path) -> None:
        with source.open("rb") as fh:
            def chunks():
                while chunk := fh.read(self.config.upload_chunk_bytes):
                    yield chunk

            response = self.control_client.put(
                self._url(f"aux/{task['id']}/artifacts/{kind}"),
                headers={
                    "X-Lease-Token": task["lease_token"],
                    "X-Content-SHA256": _sha256(source),
                    "Content-Length": str(source.stat().st_size),
                },
                content=chunks(),
                timeout=None,
            )
        self._raise(response)

    def complete_auxiliary(self, task: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.control_client.post(
            self._url(f"aux/{task['id']}/complete"),
            json={"lease_token": task["lease_token"], "metadata": metadata or {}},
        )
        self._raise(response)
        return response.json()

    def fail_auxiliary(self, task: dict[str, Any], error: str) -> None:
        response = self.control_client.post(
            self._url(f"aux/{task['id']}/fail"),
            json={"lease_token": task["lease_token"], "error": error[:8000]},
        )
        self._raise(response)

    def renew(self, task: dict[str, Any]) -> str:
        response = self.control_client.post(
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
        response = self.control_client.post(
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
        response = self.control_client.post(
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
        response = self.control_client.post(
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

    def _download_candidates(
        self,
        task: dict[str, Any],
        descriptor: dict[str, Any],
    ) -> list[tuple[str, httpx.Client, str, dict[str, str]]]:
        mode = str(descriptor.get("transfer_mode") or "proxy").lower()
        if mode == "direct":
            direct_url = str(descriptor.get("url") or "")
            if not direct_url.startswith(("http://", "https://")):
                raise RuntimeError("direct download URL must be absolute")
            direct_parts = urlsplit(direct_url)
            fallback = str(descriptor.get("fallback_url") or "")
            if direct_parts.scheme == "http" and not _is_private_or_local_host(direct_parts.hostname):
                if not fallback:
                    raise RuntimeError("public direct download URLs must use HTTPS")
                log.warning(
                    "Ignoring insecure public direct download URL for %s; using Center proxy",
                    descriptor.get("id"),
                )
                return [
                    (
                        "proxy",
                        self.control_client,
                        self._resource_url(fallback),
                        self._lease_headers(task),
                    )
                ]
            candidates: list[tuple[str, httpx.Client, str, dict[str, str]]] = [
                ("direct", self.transfer_client, direct_url, {}),
            ]
            if fallback:
                candidates.append(
                    (
                        "proxy",
                        self.control_client,
                        self._resource_url(fallback),
                        self._lease_headers(task),
                    )
                )
            return candidates
        return [
            (
                "proxy",
                self.control_client,
                self._resource_url(str(descriptor["url"])),
                self._lease_headers(task),
            )
        ]

    def download(
        self,
        task: dict[str, Any],
        descriptor: dict[str, Any],
        destination: Path,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        candidates = self._download_candidates(task, descriptor)
        last_error: Exception | None = None
        downloaded = False

        for mode_name, client, resource_url, base_headers in candidates:
            existing = part.stat().st_size if part.exists() else 0
            headers = dict(base_headers)
            if existing:
                headers["Range"] = f"bytes={existing}-"
            try:
                with client.stream("GET", resource_url, headers=headers) as response:
                    if response.status_code not in {200, 206}:
                        if mode_name == "direct":
                            raise RuntimeError(f"direct download returned HTTP {response.status_code}")
                        self._raise(response)
                    if existing and response.status_code == 200:
                        part.unlink(missing_ok=True)
                        existing = 0
                    file_mode = "ab" if existing and response.status_code == 206 else "wb"
                    with part.open(file_mode) as fh:
                        for chunk in response.iter_bytes(1024 * 1024):
                            fh.write(chunk)
                downloaded = True
                break
            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                if mode_name == "direct" and len(candidates) > 1:
                    log.warning(
                        "Direct object-store download failed for %s; falling back to Center proxy: %s",
                        descriptor.get("id"),
                        exc,
                    )
                    continue
                raise

        if not downloaded:
            raise RuntimeError(
                f"unable to download {descriptor.get('id')}: {last_error or 'no usable transfer route'}"
            )

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

    def _direct_upload_url_allowed(self, value: str) -> bool:
        parsed = urlsplit(value)
        if parsed.scheme == "https":
            return bool(parsed.netloc)
        if parsed.scheme == "http" and parsed.netloc:
            return _is_private_or_local_host(parsed.hostname)
        return False

    def _try_direct_upload(
        self,
        task: dict[str, Any],
        *,
        kind: str,
        source: Path,
        size_bytes: int,
        sha256: str,
        headers: dict[str, str],
    ) -> dict[str, Any] | None:
        session_url = self._url(f"tasks/{task['id']}/artifacts/{kind}/direct-upload")
        response = self.control_client.post(
            session_url,
            headers=headers,
            json={"size_bytes": size_bytes, "sha256": sha256},
        )
        # A V2 Worker can still talk to an older V1 Center when compatibility
        # gates are intentionally relaxed.
        if response.status_code in {404, 405}:
            return None
        self._raise(response)
        session = response.json()
        if session.get("completed") or session.get("mode") == "completed":
            if session.get("sha256") and session["sha256"] != sha256:
                raise RuntimeError(f"center already has a different {kind} artifact")
            return session
        if session.get("mode") != "direct":
            return None

        upload_url = str(session.get("upload_url") or "")
        object_key = str(session.get("object_key") or "")
        if not self._direct_upload_url_allowed(upload_url):
            log.warning("Direct upload URL is not safe/reachable for %s; using Center proxy", kind)
            return None
        if not object_key:
            raise RuntimeError("direct upload session is missing object_key")

        try:
            with source.open("rb") as fh:
                def chunks():
                    while True:
                        chunk = fh.read(1024 * 1024)
                        if not chunk:
                            return
                        yield chunk

                direct_response = self.transfer_client.put(
                    upload_url,
                    headers={"Content-Length": str(size_bytes)},
                    content=chunks(),
                )
            if not direct_response.is_success:
                log.warning(
                    "Direct object-store upload failed for %s with HTTP %s; using Center proxy",
                    kind,
                    direct_response.status_code,
                )
                return None
        except httpx.HTTPError as exc:
            log.warning("Direct object-store upload failed for %s; using Center proxy: %s", kind, exc)
            return None

        commit_url = self._url(f"tasks/{task['id']}/artifacts/{kind}/direct-commit")
        payload = {
            "object_key": object_key,
            "size_bytes": size_bytes,
            "sha256": sha256,
        }
        for retry in range(3):
            commit = self.control_client.post(commit_url, headers=headers, json=payload)
            if commit.is_success:
                return commit.json()
            # A just-written object can briefly be unavailable through some
            # S3-compatible gateways. Retry only that specific verification
            # failure; lease/auth/ownership conflicts must surface immediately.
            detail = commit.text
            if commit.status_code in {409, 503} and (
                "Direct upload object is not available" in detail
                or "Unable to verify direct upload" in detail
            ):
                if retry < 2:
                    time.sleep(0.5 * (2**retry))
                    continue
                log.warning("Direct upload commit could not verify %s; using Center proxy", kind)
                return None
            self._raise(commit)
        return None

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
        response = self.control_client.get(status_url, headers=headers)
        self._raise(response)
        status = response.json()
        if status.get("completed"):
            if status.get("sha256") and status["sha256"] != digest:
                raise RuntimeError(f"center already has a different {kind} artifact")
            return status

        total = source.stat().st_size
        direct = self._try_direct_upload(
            task,
            kind=kind,
            source=source,
            size_bytes=total,
            sha256=digest,
            headers=headers,
        )
        if direct is not None:
            return direct

        offset = int(status.get("received_bytes") or 0)
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
                response = self.control_client.put(
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
    def __init__(
        self,
        api: RemoteApi | Any,
        task: dict[str, Any],
        interval: int,
        grace_period_seconds: float = 90.0,
    ) -> None:
        self.api = api
        self.task = task
        self.interval = max(0.01, float(interval))
        self.grace_period_seconds = max(0.01, float(grace_period_seconds))
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.last_success_at = time.monotonic()
        self.thread = threading.Thread(
            target=self._loop,
            name=f"lease-{task['id']}",
            daemon=True,
        )

    def _loop(self) -> None:
        fail_count = 0
        while not self.stop_event.wait(self.interval):
            try:
                self.api.renew(self.task)
                if fail_count > 0:
                    log.info(
                        "lease renew recovered after %d failures task=%s",
                        fail_count,
                        self.task["id"],
                    )
                    fail_count = 0
                self.last_success_at = time.monotonic()
            except RemoteApiError as exc:
                if exc.status_code in {404, 409}:
                    log.error(
                        "lease renew rejected with status %s task=%s error=%s",
                        exc.status_code,
                        self.task["id"],
                        exc,
                    )
                    self.lost_event.set()
                    return
                fail_count += 1
                elapsed = time.monotonic() - self.last_success_at
                log.warning(
                    "lease renew transient error (attempt %d, elapsed %.1fs) task=%s: %s",
                    fail_count,
                    elapsed,
                    self.task["id"],
                    exc,
                )
                if elapsed >= self.grace_period_seconds:
                    log.error(
                        "lease renew grace period exceeded (%.1fs >= %.1fs) task=%s",
                        elapsed,
                        self.grace_period_seconds,
                        self.task["id"],
                    )
                    self.lost_event.set()
                    return
            except Exception as exc:  # noqa: BLE001
                fail_count += 1
                elapsed = time.monotonic() - self.last_success_at
                log.warning(
                    "lease renew network error (attempt %d, elapsed %.1fs) task=%s: %s",
                    fail_count,
                    elapsed,
                    self.task["id"],
                    exc,
                )
                if elapsed >= self.grace_period_seconds:
                    log.error(
                        "lease renew grace period exceeded (%.1fs >= %.1fs) task=%s",
                        elapsed,
                        self.grace_period_seconds,
                        self.task["id"],
                    )
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
        self.avatar_engine = ContextualMatteMuseTalkEngine(
            create_musetalk_engine(config.render_backend)
        )
        self.composer = MatteAwareCourseComposer(CourseComposer().config)

    @staticmethod
    def _attempt_root() -> Path:
        return app_settings.workspace_dir / "remote-page-worker"

    def _cleanup_stale_attempt_workspaces(self) -> None:
        root = self._attempt_root()
        if not root.exists():
            return
        for path in root.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

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
        download_started = time.time()
        files = self._download_inputs(task)
        asset_download_seconds = time.time() - download_started
        lease.checkpoint()
        self.api.progress(
            task,
            10,
            "assets_ready",
            {
                "asset_count": len(files),
                "asset_download_seconds": round(asset_download_seconds, 4),
            },
        )

        slide_artifact_id = str(payload.get("slide_artifact_id") or "")
        if not slide_artifact_id or slide_artifact_id not in files:
            raise ValueError("prepared slide artifact is missing from the task manifest")
        slide_target = work.slide_dir / f"slide-{index}.png"
        shutil.copy2(files[slide_artifact_id], slide_target)

        master_id = str(payload.get("master_video_asset_id") or "")
        if not master_id or master_id not in files:
            raise ValueError("master video asset is missing from the task manifest")
        master_path = files[master_id]
        manifest_descriptors = [
            *(task.get("assets") or []),
            *(task.get("prepared_artifacts") or []),
        ]
        master_descriptor = next(
            (
                item
                for item in manifest_descriptors
                if str(item.get("id") or "") == master_id
            ),
            None,
        )
        master_digest = str((master_descriptor or {}).get("sha256") or "").strip().lower()
        if not master_digest:
            master_digest = _sha256(master_path)
        alpha_id = str(payload.get("alpha_asset_id") or "")
        alpha_path = files.get(alpha_id) if alpha_id else None

        background_id = str(payload.get("background_asset_id") or "")
        override = dict(payload.get("override") or {})
        media_cues = payload.get("media_cues")
        if not isinstance(media_cues, list):
            media_cues = override.get("media_cues") if isinstance(override.get("media_cues"), list) else []
        override["media_cues"] = media_cues
        cue_asset_paths = {
            asset_id: files[asset_id]
            for asset_id in media_cue_asset_ids(media_cues)
            if asset_id in files
        }
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

        stage_metrics: dict[str, Any] = {
            "assets_ready": {
                "asset_count": len(files),
                "asset_download_seconds": round(asset_download_seconds, 4),
            }
        }

        def on_stage(stage: str, detail: dict[str, Any]) -> None:
            lease.checkpoint()
            mapping = {
                "audio_start": 20,
                "audio_done": 35,
                "video_start": 40,
                "video_done": 75,
                "video_skipped": 75,
                "compose_start": 80,
                "media_cue_start": 86,
                "media_cue_done": 90,
                "compose_done": 92,
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
                master_cache_key=f"remote:{master_id}:{master_digest}",
                job_id=task["parent_job_id"],
                settings_payload=course_settings,
                prepared_audio=prepared_audio,
                prepared_audio_source=prepared_audio_source,
                media_cue_assets=cue_asset_paths,
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
        render_metadata = dict(result.metadata or {})
        metrics = {
            "asset_download_seconds": round(asset_download_seconds, 4),
            "tts_elapsed_seconds": result.tts_elapsed_seconds,
            "render_seconds": result.render_seconds,
            "compose_seconds": result.compose_seconds,
            "media_cue_seconds": result.media_cue_seconds,
            "audio_source": result.audio_source,
            "video_encoder": render_metadata.get("video_encoder"),
            "compose_video_encoder": render_metadata.get("compose_video_encoder"),
            "media_cue_video_encoder": render_metadata.get("media_cue_video_encoder"),
            "render_pipeline": render_metadata.get("pipeline"),
            "cuda_timings": render_metadata.get("cuda_timings", {}),
            "media_cues": render_metadata.get("media_cues", []),
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
        attempt_work = self._attempt_root() / task["attempt_id"]
        try:
            with LeaseKeeper(
                self.api,
                task,
                saas_settings.distributed_renew_seconds,
            ) as lease:
                video, audio, media, metrics = self._execute(task, lease)
                lease.checkpoint()
                self.api.progress(task, 92, "uploading", metrics)
                upload_audio_started = time.time()
                self.api.upload(task, kind="page_audio", source=audio)
                metrics["upload_audio_seconds"] = round(time.time() - upload_audio_started, 4)
                lease.checkpoint()
                upload_video_started = time.time()
                self.api.upload(task, kind="page_video", source=video)
                metrics["upload_video_seconds"] = round(time.time() - upload_video_started, 4)
                metrics["upload_total_seconds"] = round(
                    metrics["upload_audio_seconds"] + metrics["upload_video_seconds"],
                    4,
                )
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
            try:
                self.cache.release_all()
            finally:
                shutil.rmtree(attempt_work, ignore_errors=True)

    def process_auxiliary_task(self, task: dict[str, Any]) -> None:
        self._current_task_id = task["id"]
        self._last_error = None
        work = self._attempt_root() / f"aux-{task['id']}"
        work.mkdir(parents=True, exist_ok=True)
        # The common downloader sends both headers for proxy transfers. Auxiliary
        # endpoints need only the lease token but use the same verified download.
        task["attempt_id"] = task["id"]
        try:
            with LeaseKeeper(
                SimpleNamespace(renew=self.api.renew_auxiliary),
                task,
                saas_settings.distributed_renew_seconds,
            ) as lease:
                inputs: dict[str, Path] = {}
                for descriptor in task["assets"]:
                    suffix = Path(descriptor["name"]).suffix or ".bin"
                    inputs[descriptor["id"]] = self.api.download(
                        task, descriptor, work / f"{descriptor['id']}{suffix}"
                    )
                lease.checkpoint()
                payload = task["payload"]
                if task["kind"] == "avatar_matting":
                    engine = PortraitMattingEngine(model=payload["model"])
                    result = engine.process(
                        inputs[payload["source_asset_id"]],
                        work,
                        progress=lambda pct, stage: self.api.progress_auxiliary(task, min(90, pct), stage),
                    )
                    metadata = {
                        "fps": round(result.fps, 6),
                        "frames": result.frame_count,
                        "width": result.width,
                        "height": result.height,
                        "model": result.model,
                        "backend": result.backend,
                        "foreground_recovery": result.foreground_recovery,
                        "foreground_recovered_ratio": round(result.foreground_recovered_ratio, 4),
                        "enclosed_foreground_recovered_ratio": round(
                            getattr(result, "enclosed_foreground_recovered_ratio", 0.0), 4
                        ),
                        "green_screen": result.green_screen,
                        "elapsed_seconds": round(result.elapsed_seconds, 2),
                        "temporal_smoothing": engine.temporal_smoothing,
                        "edge_blur": engine.edge_blur,
                    }
                    outputs = {
                        "alpha": result.alpha_video,
                        "poster": result.poster_png,
                        "white": result.white_preview,
                    }
                else:
                    voice = self._voice_proxy(payload["voice"])
                    runtime = build_course_tts(
                        voice,
                        ref_audio=inputs[payload["reference_asset_id"]],
                        course_settings=payload["course_settings"],
                        base=work,
                    )
                    try:
                        output = synthesize_course_audio(runtime, payload["text"], work / "preview.wav")
                    finally:
                        release = getattr(runtime.provider, "release", None)
                        if callable(release):
                            release()
                    metadata = {}
                    outputs = {"audio": output}
                lease.checkpoint()
                self.api.progress_auxiliary(task, 92, "uploading")
                for kind, output in outputs.items():
                    self.api.upload_auxiliary(task, kind, output)
                    lease.checkpoint()
                self.api.complete_auxiliary(task, metadata)
        except LeaseLost:
            log.warning("Auxiliary lease lost for task %s", task["id"])
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            log.exception("Remote auxiliary task failed task=%s", task["id"])
            try:
                self.api.fail_auxiliary(task, str(exc))
            except Exception as report_exc:  # noqa: BLE001
                log.warning("Unable to report auxiliary task failure: %s", report_exc)
        finally:
            self._current_task_id = None
            shutil.rmtree(work, ignore_errors=True)

    def run_forever(self) -> None:
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_attempt_workspaces()
        self.register()
        heartbeat = self.start_heartbeat()
        prefer_auxiliary = False
        try:
            while not self._stop.is_set():
                if not self._disk_ready():
                    self._last_error = "disk free below configured safety threshold"
                    try:
                        self.api.heartbeat(error=self._last_error)
                    except Exception:
                        pass
                    self.cache.cleanup()
                    self._cleanup_stale_attempt_workspaces()
                    time.sleep(5)
                    continue
                self._last_error = None
                try:
                    auxiliary = self.api.claim_auxiliary() if prefer_auxiliary else None
                    task = None if auxiliary else self.api.claim()
                    if task is None and auxiliary is None and not prefer_auxiliary:
                        auxiliary = self.api.claim_auxiliary()
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    log.warning("Task claim failed: %s", exc)
                    time.sleep(3)
                    continue
                if task is None and auxiliary is None:
                    time.sleep(1)
                    continue
                prefer_auxiliary = not prefer_auxiliary
                if auxiliary is not None:
                    self.process_auxiliary_task(auxiliary)
                else:
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
