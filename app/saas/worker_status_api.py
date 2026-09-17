from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .distributed_render_models import WorkerNode
from .security import Principal, get_principal
from .settings import saas_settings


router = APIRouter(prefix="/workers", tags=["workers"])


def _legacy_status() -> dict:
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


def _distributed_nodes(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    items = db.scalars(select(WorkerNode).order_by(WorkerNode.name.asc(), WorkerNode.created_at.asc())).all()
    nodes: list[dict] = []
    for item in items:
        last_seen = item.last_seen_at
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        heartbeat_age = (now - last_seen).total_seconds() if last_seen else None
        effective_online = bool(
            last_seen
            and heartbeat_age is not None
            and heartbeat_age <= max(30, saas_settings.distributed_lease_seconds)
            and item.status not in {"revoked", "incompatible"}
        )
        nodes.append(
            {
                "id": item.id,
                "name": item.name,
                "status": item.status if effective_online else (item.status if item.status in {"revoked", "incompatible"} else "offline"),
                "online": effective_online,
                "accepting_tasks": item.accepting_tasks,
                "slots_total": item.slots_total,
                "slots_busy": item.slots_busy,
                "current_task_id": item.current_task_id,
                "machine": item.machine,
                "code_version": item.code_version,
                "model_version": item.model_version,
                "render_contract_version": item.render_contract_version,
                "disk_free_bytes": item.disk_free_bytes,
                "memory_available_mb": item.memory_available_mb,
                "last_error": item.last_error,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
        )
    return nodes


@router.get("/status")
def worker_status(
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    del principal
    nodes = _distributed_nodes(db)
    return {
        "backend": saas_settings.worker_backend,
        "engines": _legacy_status(),
        "distributed": {
            "enabled": saas_settings.distributed_render_enabled,
            "render_contract_version": saas_settings.render_contract_version,
            "online_count": sum(bool(node["online"]) for node in nodes),
            "busy_count": sum(int(node["slots_busy"] or 0) > 0 for node in nodes),
            "nodes": nodes,
        },
    }
