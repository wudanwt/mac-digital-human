from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from sqlalchemy import text

from ..engines import MuseTalkMLXEngine
from ..tts.cosyvoice import CosyVoiceTTS
from .avatar_matting_engine import PortraitMattingEngine
from .database import engine
from .settings import saas_settings
from .storage import object_store


def collect(remote_api_base: str | None = None) -> dict:
    checks: dict[str, object] = {
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
        },
        "ffmpeg": bool(shutil.which("ffmpeg")),
    }

    if remote_api_base is None:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as exc:
            checks["database"] = str(exc)

        try:
            import redis

            client = redis.Redis.from_url(saas_settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            checks["redis"] = True
        except Exception as exc:
            checks["redis"] = str(exc)

        try:
            object_store.healthcheck()
            root = Path(saas_settings.storage_local_root).resolve() if saas_settings.storage_backend == "local" else None
            checks["storage"] = {"ready": True, "root": str(root) if root else saas_settings.storage_backend}
        except Exception as exc:
            checks["storage"] = {"ready": False, "error": str(exc)}
    else:
        parsed = urlsplit(remote_api_base.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path.endswith("/internal/render"):
            checks["center_api"] = {"ready": False, "error": "invalid remote API base URL"}
        else:
            health_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path[:-len('/internal/render')]}/health"
            try:
                with httpx.Client(trust_env=False, timeout=5.0) as client:
                    response = client.get(health_url)
                response.raise_for_status()
                payload = response.json()
                checks["center_api"] = {"ready": isinstance(payload, dict) and payload.get("status") == "ok"}
            except Exception as exc:
                checks["center_api"] = {"ready": False, "error": str(exc)}

    try:
        checks["musetalk"] = MuseTalkMLXEngine().readiness()
    except Exception as exc:
        checks["musetalk"] = {"ready": False, "error": str(exc)}

    try:
        checks["cosyvoice"] = CosyVoiceTTS().readiness()
    except Exception as exc:
        checks["cosyvoice"] = {"ready": False, "error": str(exc)}

    try:
        checks["portrait_matting"] = PortraitMattingEngine.readiness()
    except Exception as exc:
        checks["portrait_matting"] = {"ready": False, "error": str(exc)}

    if remote_api_base is None:
        control_plane_ready = bool(
            checks["database"] is True
            and checks["redis"] is True
            and isinstance(checks["storage"], dict)
            and checks["storage"].get("ready") is True
        )
    else:
        control_plane_ready = bool(checks["center_api"].get("ready"))

    ready = bool(
        checks["platform"]["apple_silicon"]
        and checks["ffmpeg"]
        and control_plane_ready
        and isinstance(checks["musetalk"], dict)
        and checks["musetalk"].get("ready") is True
        and isinstance(checks["cosyvoice"], dict)
        and checks["cosyvoice"].get("ready") is True
        and isinstance(checks["portrait_matting"], dict)
        and checks["portrait_matting"].get("ready") is True
    )
    return {"ready": ready, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-api", help="API base for an API-only page worker")
    args = parser.parse_args()
    payload = collect(remote_api_base=args.remote_api)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
