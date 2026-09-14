from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import TTSError


@dataclass(frozen=True)
class Audio8Config:
    base_url: str = "http://127.0.0.1:8024"
    voice: str = "default"
    runtime_dir: str | None = None
    auto_start: bool = True
    threads: int = 5
    max_new_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    seed: int = 42
    ref_audio: str | None = None
    ref_text: str | None = None
    overwrite_voice: bool = False


class Audio8ONNXTTS:
    """Production TTS backed by Audio8 0.1B INT8 ONNX CPU runtime.

    The Audio8 runtime is intentionally kept in its own virtual environment and
    exposed through its local HTTP service. This avoids mixing ONNX/runtime
    dependencies with the MLX video stack and keeps the model warm across a
    whole course batch.
    """

    name = "audio8"

    def __init__(self, config: Audio8Config | None = None) -> None:
        self.config = config or Audio8Config()
        self.base_url = self.config.base_url.rstrip("/")
        root = Path(__file__).resolve().parents[2]
        self.runtime_dir = Path(
            self.config.runtime_dir
            or os.getenv(
                "AUDIO8_RUNTIME_DIR",
                str(root / "vendor" / "Audio8_TTS" / "onnx_runtime_0_1b_int8"),
            )
        ).expanduser()
        self._voice_ready = False

    def _request(self, path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 120) -> bytes:
        req = Request(self.base_url + path, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
        try:
            with urlopen(req, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise TTSError(f"Audio8 HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise TTSError(f"Audio8 service unavailable: {exc}") from exc

    def _json(self, path: str, *, payload: dict | None = None, timeout: int = 120) -> dict:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        raw = self._request(path, data=data, headers=headers, timeout=timeout)
        return json.loads(raw.decode("utf-8"))

    def health(self) -> dict | None:
        try:
            return self._json("/api/health", timeout=3)
        except Exception:
            return None

    def readiness(self) -> dict:
        health = self.health()
        return {
            "provider": self.name,
            "ready": bool(health and health.get("ok")),
            "service_url": self.base_url,
            "runtime_dir": str(self.runtime_dir),
            "runtime_installed": (self.runtime_dir / ".venv").exists(),
            "model_installed": (self.runtime_dir / "model").exists(),
            "voice": self.config.voice,
            "health": health,
        }

    def _start_server(self) -> None:
        if self.health():
            return
        if not self.config.auto_start:
            raise TTSError(f"Audio8 service is not running: {self.base_url}")
        parsed = urlparse(self.base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise TTSError("Audio8 auto-start is only supported for localhost services")
        start_script = self.runtime_dir / "start_server.sh"
        if not start_script.exists():
            raise TTSError("Audio8 runtime not installed; run: bash scripts/setup_audio8.sh")
        env = os.environ.copy()
        env["PORT"] = str(parsed.port or 8024)
        env["ARKTTS_THREADS"] = str(self.config.threads)
        try:
            subprocess.run(
                ["bash", str(start_script)],
                cwd=self.runtime_dir,
                env=env,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise TTSError("Audio8 service failed to start; inspect vendor/Audio8_TTS/onnx_runtime_0_1b_int8/service.log") from exc
        if not self.health():
            raise TTSError("Audio8 service did not become healthy after startup")

    @staticmethod
    def _multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
        boundary = "----MacDigitalHuman" + uuid.uuid4().hex
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
                b"Content-Type: audio/wav\r\n\r\n",
                file_path.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def register_voice(self, *, name: str, audio: Path, text: str, overwrite: bool = False) -> dict:
        if not audio.exists():
            raise TTSError(f"Audio8 reference audio not found: {audio}")
        if not text.strip():
            raise TTSError("Audio8 voice cloning requires an accurate reference transcript")
        self._start_server()
        body, content_type = self._multipart(
            {"name": name, "text": text, "overwrite": "true" if overwrite else "false"},
            "audio",
            audio,
        )
        req = Request(
            self.base_url + "/api/voices/register",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urlopen(req, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 409 and not overwrite:
                return {"ok": True, "voice": {"name": name, "existing": True}}
            detail = exc.read().decode("utf-8", errors="replace")
            raise TTSError(f"Audio8 voice registration failed ({exc.code}): {detail}") from exc
        except URLError as exc:
            raise TTSError(f"Audio8 voice registration unavailable: {exc}") from exc

    def _ensure_configured_voice(self) -> None:
        if self._voice_ready:
            return
        if self.config.ref_audio:
            if self.config.voice == "default":
                raise TTSError("Audio8 cloned voice needs a non-default voice name")
            self.register_voice(
                name=self.config.voice,
                audio=Path(self.config.ref_audio).expanduser(),
                text=self.config.ref_text or "",
                overwrite=self.config.overwrite_voice,
            )
        self._voice_ready = True

    def synthesize(self, text: str, output: Path, **_: object) -> Path:
        if not text.strip():
            raise TTSError("TTS text must not be empty")
        self._start_server()
        self._ensure_configured_voice()
        payload = {
            "text": text,
            "voice_name": self.config.voice,
            "max_new_tokens": self.config.max_new_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "seed": self.config.seed,
        }
        raw = self._request(
            "/api/tts",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=600,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        return output

    def release(self) -> None:
        # Keep the small CPU runtime warm for the complete course batch. It is
        # isolated from the MLX process and can be stopped explicitly via
        # scripts/stop_audio8.sh when desired.
        return None
