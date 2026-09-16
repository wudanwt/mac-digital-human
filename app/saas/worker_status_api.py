from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends

from .security import Principal, get_principal
from .settings import saas_settings


router = APIRouter(prefix="/workers", tags=["workers"])


def _status() -> dict:
    result = {
        "mock": {"online": False, "count": 0},
        "musetalk": {"online": False, "count": 0},
        "cuda-musetalk": {"online": False, "count": 0},
    }
    if saas_settings.worker_backend != "redis":
        return result
    try:
        import redis

        client = redis.Redis.from_url(saas_settings.redis_url, decode_responses=True)
        pattern = f"{saas_settings.queue_name}:worker:*"
        for key in client.scan_iter(match=pattern, count=100):
            raw = client.get(key)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            engine = str(payload.get("engine") or "")
            if engine not in result:
                result[engine] = {"online": False, "count": 0}
            result[engine]["count"] += 1
            result[engine]["online"] = True
    except Exception:
        pass
    return result


@router.get("/status")
def worker_status(
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict:
    del principal
    return {"backend": saas_settings.worker_backend, "engines": _status()}
