from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from .distributed_render_models import RenderAttempt, RenderSubtask, WorkerNode
from .models import Course, RenderJobRecord
from .render_snapshot_models import RenderTaskSnapshot
from .services import refund_render_seconds
from .settings import saas_settings

ACTIVE_PARENT_STATES = {"queued", "running"}
RETRYABLE_TASK_STATES = {"queued", "retry_wait"}
TERMINAL_TASK_STATES = {"succeeded", "failed", "canceled"}


class SchedulerError(RuntimeError):
    pass


class LeaseConflict(SchedulerError):
    pass


@dataclass(frozen=True)
class TaskLease:
    task_id: str
    parent_job_id: str
    tenant_id: str
    slide_index: int
    attempt_id: str
    attempt_no: int
    lease_token: str
    lease_expires_at: datetime
    config_hash: str
    payload: dict[str, Any]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except Exception:
        return fallback
    return parsed


def _parent_priority(parent: RenderJobRecord) -> int:
    payload = _json(parent.payload_json, {})
    try:
        return int(payload.get("priority", 0)) if isinstance(payload, dict) else 0
    except (TypeError, ValueError):
        return 0


def _snapshot(db: Session, parent_job_id: str) -> tuple[RenderJobRecord, RenderTaskSnapshot, dict[str, Any]]:
    parent = db.get(RenderJobRecord, parent_job_id)
    snapshot = db.get(RenderTaskSnapshot, parent_job_id)
    if parent is None or snapshot is None:
        raise SchedulerError("render parent or immutable snapshot not found")
    payload = _json(snapshot.snapshot_json, {})
    if not isinstance(payload, dict):
        raise SchedulerError("render snapshot is invalid")
    return parent, snapshot, payload


def initialize_parent_graph(db: Session, parent_job_id: str) -> tuple[RenderSubtask, RenderSubtask]:
    """Create the center-only prepare/finalize skeleton idempotently.

    Page tasks are deliberately not created yet: the real PPT page count is only
    authoritative after the center prepare step parses the frozen deck.
    """

    parent, snapshot, _ = _snapshot(db, parent_job_id)
    priority = _parent_priority(parent)
    now = utcnow()

    prepare = db.scalar(
        select(RenderSubtask).where(
            RenderSubtask.parent_job_id == parent_job_id,
            RenderSubtask.task_type == "prepare",
            RenderSubtask.slide_index == 0,
        )
    )
    if prepare is None:
        payload = {"task_type": "prepare", "snapshot_hash": snapshot.snapshot_hash}
        prepare = RenderSubtask(
            tenant_id=parent.tenant_id,
            parent_job_id=parent.id,
            task_type="prepare",
            slide_index=0,
            config_hash=canonical_hash(payload),
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            status="queued",
            priority=priority,
            progress=0,
            stage="queued",
            available_at=now,
        )
        db.add(prepare)

    finalize = db.scalar(
        select(RenderSubtask).where(
            RenderSubtask.parent_job_id == parent_job_id,
            RenderSubtask.task_type == "finalize",
            RenderSubtask.slide_index == 0,
        )
    )
    if finalize is None:
        payload = {"task_type": "finalize", "snapshot_hash": snapshot.snapshot_hash}
        finalize = RenderSubtask(
            tenant_id=parent.tenant_id,
            parent_job_id=parent.id,
            task_type="finalize",
            slide_index=0,
            config_hash=canonical_hash(payload),
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            status="blocked",
            priority=priority,
            progress=0,
            stage="waiting_pages",
            blocked_reason="waiting for prepare and page tasks",
        )
        db.add(finalize)
    db.flush()
    return prepare, finalize


def publish_prepared_pages(
    db: Session,
    *,
    parent_job_id: str,
    pages: list[dict[str, Any]],
    prepared_manifest: dict[str, Any] | None = None,
) -> list[RenderSubtask]:
    """Complete center preparation and publish one immutable task per real page."""

    parent, snapshot, snapshot_payload = _snapshot(db, parent_job_id)
    if parent.status not in ACTIVE_PARENT_STATES:
        raise SchedulerError(f"parent job is not active: {parent.status}")
    prepare, finalize = initialize_parent_graph(db, parent_job_id)
    priority = _parent_priority(parent)
    now = utcnow()

    prepared_pages: list[RenderSubtask] = []
    seen: set[int] = set()
    for position, raw in enumerate(pages, start=1):
        page = dict(raw)
        index = int(page.get("index") or position)
        if index <= 0 or index in seen:
            raise SchedulerError(f"invalid or duplicate prepared page index: {index}")
        seen.add(index)
        page["index"] = index
        page.setdefault("snapshot_hash", snapshot.snapshot_hash)
        page.setdefault("render_contract_version", saas_settings.render_contract_version)
        narration = str(page.get("narration") or "")
        estimate = page.get("estimated_seconds")
        try:
            estimate_value = float(estimate) if estimate is not None else max(4.0, len(narration) / 4.0)
        except (TypeError, ValueError):
            estimate_value = max(4.0, len(narration) / 4.0)
        digest = canonical_hash(page)

        task = db.scalar(
            select(RenderSubtask).where(
                RenderSubtask.parent_job_id == parent_job_id,
                RenderSubtask.task_type == "page",
                RenderSubtask.slide_index == index,
            )
        )
        if task is None:
            task = RenderSubtask(
                tenant_id=parent.tenant_id,
                parent_job_id=parent_job_id,
                task_type="page",
                slide_index=index,
                config_hash=digest,
                payload_json=json.dumps(page, ensure_ascii=False, sort_keys=True),
                status="queued",
                priority=priority,
                estimated_seconds=estimate_value,
                progress=0,
                stage="queued",
                available_at=now,
            )
            db.add(task)
        elif task.status in {"blocked", "queued"}:
            # Preparation may be retried after a center restart. Only unstarted
            # tasks may be refreshed; running/terminal task inputs are immutable.
            task.config_hash = digest
            task.payload_json = json.dumps(page, ensure_ascii=False, sort_keys=True)
            task.estimated_seconds = estimate_value
            task.status = "queued"
            task.stage = "queued"
            task.blocked_reason = None
            task.available_at = now
        elif task.config_hash != digest:
            raise SchedulerError(f"prepared page changed after execution started: {index}")
        prepared_pages.append(task)

    existing_pages = db.scalars(
        select(RenderSubtask).where(
            RenderSubtask.parent_job_id == parent_job_id,
            RenderSubtask.task_type == "page",
        )
    ).all()
    unexpected = [task.slide_index for task in existing_pages if task.slide_index not in seen]
    if unexpected:
        raise SchedulerError(f"prepared page set changed after publication: {unexpected}")

    prepare.status = "succeeded"
    prepare.progress = 100
    prepare.stage = "completed"
    prepare.error = None
    prepare.completed_at = now
    prepare.payload_json = json.dumps(
        {
            **_json(prepare.payload_json, {}),
            "prepared_manifest": prepared_manifest or {},
            "page_count": len(prepared_pages),
            "snapshot_hash": snapshot_payload.get("snapshot_hash") or snapshot.snapshot_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    finalize.status = "blocked" if prepared_pages else "queued"
    finalize.stage = "waiting_pages" if prepared_pages else "queued"
    finalize.blocked_reason = "waiting for page tasks" if prepared_pages else None
    finalize.available_at = None if prepared_pages else now
    parent.status = "running"
    parent.stage = "distributed_pages" if prepared_pages else "distributed_finalize"
    if parent.started_at is None:
        parent.started_at = now
    db.flush()
    return sorted(prepared_pages, key=lambda item: item.slide_index)


def _claim_query(now: datetime):
    # Fairness is evaluated within a subscription-priority tier. Tenants and then
    # parent courses that have not received a recent slot are selected first;
    # only then do we prefer longer pages to reduce tail latency.
    hist_task = aliased(RenderSubtask)
    hist_attempt = aliased(RenderAttempt)
    tenant_last = (
        select(func.max(hist_attempt.claimed_at))
        .join(hist_task, hist_task.id == hist_attempt.subtask_id)
        .where(hist_task.tenant_id == RenderSubtask.tenant_id)
        .correlate(RenderSubtask)
        .scalar_subquery()
    )
    parent_last = (
        select(func.max(hist_attempt.claimed_at))
        .join(hist_task, hist_task.id == hist_attempt.subtask_id)
        .where(hist_task.parent_job_id == RenderSubtask.parent_job_id)
        .correlate(RenderSubtask)
        .scalar_subquery()
    )
    return (
        select(RenderSubtask)
        .join(RenderJobRecord, RenderJobRecord.id == RenderSubtask.parent_job_id)
        .where(
            RenderSubtask.task_type == "page",
            RenderSubtask.status.in_(RETRYABLE_TASK_STATES),
            or_(RenderSubtask.available_at.is_(None), RenderSubtask.available_at <= now),
            RenderJobRecord.status.in_(ACTIVE_PARENT_STATES),
        )
        .order_by(
            RenderSubtask.priority.desc(),
            tenant_last.asc().nullsfirst(),
            parent_last.asc().nullsfirst(),
            RenderSubtask.estimated_seconds.desc().nullslast(),
            RenderSubtask.created_at.asc(),
            RenderSubtask.slide_index.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )


def claim_page_task(db: Session, *, node_id: str) -> TaskLease | None:
    """Atomically lease one page to a compatible node.

    PostgreSQL's SKIP LOCKED lets all Macs call this concurrently without Redis
    task ownership. SQLite ignores the row-lock clause and remains suitable only
    for single-process development.
    """

    now = utcnow()
    node = db.scalar(select(WorkerNode).where(WorkerNode.id == node_id).with_for_update())
    if node is None:
        raise SchedulerError("worker node not found")
    if not node.accepting_tasks:
        return None
    if node.slots_busy >= max(1, node.slots_total):
        return None
    if node.render_contract_version and node.render_contract_version != saas_settings.render_contract_version:
        raise SchedulerError(
            f"worker render contract mismatch: {node.render_contract_version} != {saas_settings.render_contract_version}"
        )

    task = db.scalar(_claim_query(now))
    if task is None:
        return None

    token = secrets.token_urlsafe(32)
    expiry = now + timedelta(seconds=max(30, saas_settings.distributed_lease_seconds))
    attempt_no = int(task.attempt_count or 0) + 1
    attempt = RenderAttempt(
        subtask_id=task.id,
        node_id=node.id,
        attempt_no=attempt_no,
        lease_token_hash=hash_secret(token),
        status="running",
        progress=0,
        stage="claimed",
        metrics_json=json.dumps({"_progress_at": now.isoformat()}, ensure_ascii=False, sort_keys=True),
        claimed_at=now,
        lease_expires_at=expiry,
        last_renewed_at=now,
    )
    db.add(attempt)
    db.flush()

    task.status = "running"
    task.stage = "claimed"
    task.progress = 0
    task.assigned_node_id = node.id
    task.active_attempt_id = attempt.id
    task.lease_expires_at = expiry
    task.attempt_count = attempt_no
    task.available_at = None
    task.error = None
    if task.started_at is None:
        task.started_at = now

    node.status = "busy"
    node.slots_busy = min(max(1, node.slots_total), int(node.slots_busy or 0) + 1)
    node.current_task_id = task.id
    node.last_seen_at = now

    parent = db.get(RenderJobRecord, task.parent_job_id)
    if parent is not None and parent.status in ACTIVE_PARENT_STATES:
        parent.status = "running"
        parent.stage = "distributed_pages"
        if parent.started_at is None:
            parent.started_at = now
    db.flush()

    payload = _json(task.payload_json, {})
    return TaskLease(
        task_id=task.id,
        parent_job_id=task.parent_job_id,
        tenant_id=task.tenant_id,
        slide_index=task.slide_index,
        attempt_id=attempt.id,
        attempt_no=attempt_no,
        lease_token=token,
        lease_expires_at=expiry,
        config_hash=task.config_hash,
        payload=payload if isinstance(payload, dict) else {},
    )


def _active_attempt(
    db: Session,
    *,
    task_id: str,
    attempt_id: str,
    node_id: str,
    lease_token: str,
    allow_expired: bool = False,
) -> tuple[RenderSubtask, RenderAttempt, WorkerNode]:
    now = utcnow()
    task = db.scalar(select(RenderSubtask).where(RenderSubtask.id == task_id).with_for_update())
    if task is None:
        raise LeaseConflict("task not found")
    attempt = db.scalar(select(RenderAttempt).where(RenderAttempt.id == attempt_id).with_for_update())
    node = db.scalar(select(WorkerNode).where(WorkerNode.id == node_id).with_for_update())
    if attempt is None or node is None:
        raise LeaseConflict("attempt or worker node not found")
    if task.status != "running" or task.active_attempt_id != attempt.id or task.assigned_node_id != node.id:
        raise LeaseConflict("attempt is no longer active for this task")
    if attempt.subtask_id != task.id or attempt.node_id != node.id or attempt.status != "running":
        raise LeaseConflict("attempt ownership mismatch")
    if not hmac.compare_digest(attempt.lease_token_hash, hash_secret(lease_token)):
        raise LeaseConflict("invalid lease token")
    if not allow_expired and (task.lease_expires_at is None or task.lease_expires_at <= now or attempt.lease_expires_at <= now):
        raise LeaseConflict("lease has expired")
    return task, attempt, node


def renew_lease(
    db: Session,
    *,
    task_id: str,
    attempt_id: str,
    node_id: str,
    lease_token: str,
) -> datetime:
    task, attempt, node = _active_attempt(
        db,
        task_id=task_id,
        attempt_id=attempt_id,
        node_id=node_id,
        lease_token=lease_token,
    )
    now = utcnow()
    expiry = now + timedelta(seconds=max(30, saas_settings.distributed_lease_seconds))
    task.lease_expires_at = expiry
    attempt.lease_expires_at = expiry
    attempt.last_renewed_at = now
    node.last_seen_at = now
    db.flush()
    return expiry


def report_progress(
    db: Session,
    *,
    task_id: str,
    attempt_id: str,
    node_id: str,
    lease_token: str,
    progress: int,
    stage: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    task, attempt, node = _active_attempt(
        db,
        task_id=task_id,
        attempt_id=attempt_id,
        node_id=node_id,
        lease_token=lease_token,
    )
    now = utcnow()
    value = max(0, min(99, int(progress)))
    task.progress = value
    task.stage = str(stage or "running")[:80]
    attempt.progress = value
    attempt.stage = task.stage
    progress_metrics = dict(metrics or {})
    progress_metrics["_progress_at"] = now.isoformat()
    attempt.metrics_json = json.dumps(progress_metrics, ensure_ascii=False, sort_keys=True)
    node.last_seen_at = now
    db.flush()


def _release_node(node: WorkerNode, task_id: str) -> None:
    node.slots_busy = max(0, int(node.slots_busy or 0) - 1)
    if node.current_task_id == task_id:
        node.current_task_id = None
    node.status = "online" if node.accepting_tasks else "draining"
    node.last_seen_at = utcnow()


def _queue_finalize_if_ready(db: Session, parent_job_id: str) -> bool:
    pages = db.scalars(
        select(RenderSubtask).where(
            RenderSubtask.parent_job_id == parent_job_id,
            RenderSubtask.task_type == "page",
        )
    ).all()
    if not pages or any(page.status != "succeeded" for page in pages):
        return False
    finalize = db.scalar(
        select(RenderSubtask).where(
            RenderSubtask.parent_job_id == parent_job_id,
            RenderSubtask.task_type == "finalize",
            RenderSubtask.slide_index == 0,
        ).with_for_update()
    )
    if finalize is None or finalize.status in TERMINAL_TASK_STATES:
        return False
    finalize.status = "queued"
    finalize.stage = "queued"
    finalize.blocked_reason = None
    finalize.available_at = utcnow()
    parent = db.get(RenderJobRecord, parent_job_id)
    if parent is not None and parent.status in ACTIVE_PARENT_STATES:
        parent.stage = "distributed_finalize"
    return True


def complete_page_task(
    db: Session,
    *,
    task_id: str,
    attempt_id: str,
    node_id: str,
    lease_token: str,
    metrics: dict[str, Any] | None = None,
) -> bool:
    task, attempt, node = _active_attempt(
        db,
        task_id=task_id,
        attempt_id=attempt_id,
        node_id=node_id,
        lease_token=lease_token,
    )
    now = utcnow()
    attempt.status = "succeeded"
    attempt.progress = 100
    attempt.stage = "completed"
    attempt.completed_at = now
    if metrics is not None:
        attempt.metrics_json = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
    task.status = "succeeded"
    task.progress = 100
    task.stage = "completed"
    task.completed_at = now
    task.lease_expires_at = None
    task.active_attempt_id = None
    task.assigned_node_id = None
    task.error = None
    _release_node(node, task.id)
    queued_finalize = _queue_finalize_if_ready(db, task.parent_job_id)
    db.flush()
    return queued_finalize


def _fail_parent(db: Session, parent: RenderJobRecord, message: str) -> None:
    if parent.status in {"failed", "canceled", "succeeded"}:
        return
    now = utcnow()
    parent.status = "failed"
    parent.stage = "page_failed"
    parent.error = message
    parent.completed_at = now
    refund_render_seconds(
        db,
        tenant_id=parent.tenant_id,
        user_id=parent.user_id,
        job_id=parent.id,
        seconds=parent.estimated_seconds,
    )
    if parent.course_id:
        course = db.get(Course, parent.course_id)
        if course and course.status != "completed":
            course.status = "draft"


def _retry_or_fail(
    db: Session,
    *,
    task: RenderSubtask,
    attempt: RenderAttempt,
    node: WorkerNode,
    error: str,
    retryable: bool,
) -> bool:
    now = utcnow()
    attempt.status = "failed"
    attempt.error = error
    attempt.completed_at = now
    task.error = error
    task.lease_expires_at = None
    task.active_attempt_id = None
    task.assigned_node_id = None
    _release_node(node, task.id)

    can_retry = retryable and int(task.attempt_count or 0) < max(1, saas_settings.distributed_max_attempts)
    if can_retry:
        backoff = min(60, 5 * (2 ** max(0, int(task.attempt_count or 1) - 1)))
        task.status = "retry_wait"
        task.stage = "retry_wait"
        task.progress = 0
        task.available_at = now + timedelta(seconds=backoff)
        return True

    task.status = "failed"
    task.stage = "failed"
    task.completed_at = now
    parent = db.get(RenderJobRecord, task.parent_job_id)
    if parent is not None:
        _fail_parent(db, parent, error)
    return False


def fail_page_task(
    db: Session,
    *,
    task_id: str,
    attempt_id: str,
    node_id: str,
    lease_token: str,
    error: str,
    retryable: bool,
    metrics: dict[str, Any] | None = None,
) -> bool:
    task, attempt, node = _active_attempt(
        db,
        task_id=task_id,
        attempt_id=attempt_id,
        node_id=node_id,
        lease_token=lease_token,
    )
    if metrics is not None:
        attempt.metrics_json = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
    retried = _retry_or_fail(
        db,
        task=task,
        attempt=attempt,
        node=node,
        error=str(error or "page task failed"),
        retryable=bool(retryable),
    )
    db.flush()
    return retried


def _attempt_progress_at(attempt: RenderAttempt) -> datetime:
    payload = _json(attempt.metrics_json, {})
    raw = payload.get("_progress_at") if isinstance(payload, dict) else None
    if raw:
        try:
            value = datetime.fromisoformat(str(raw))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    claimed = attempt.claimed_at
    return claimed if claimed.tzinfo else claimed.replace(tzinfo=timezone.utc)


def reap_stalled_page_attempts(db: Session) -> int:
    """Retry workers that renew leases but make no stage progress for too long."""

    now = utcnow()
    cutoff = now - timedelta(seconds=max(60, saas_settings.distributed_stall_seconds))
    tasks = db.scalars(
        select(RenderSubtask)
        .where(
            RenderSubtask.task_type == "page",
            RenderSubtask.status == "running",
            RenderSubtask.active_attempt_id.is_not(None),
        )
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for task in tasks:
        attempt = db.get(RenderAttempt, task.active_attempt_id) if task.active_attempt_id else None
        node = db.get(WorkerNode, task.assigned_node_id) if task.assigned_node_id else None
        if attempt is None or node is None or attempt.status != "running":
            continue
        if _attempt_progress_at(attempt) > cutoff:
            continue
        error = (
            f"worker made no stage progress for {max(60, saas_settings.distributed_stall_seconds)} seconds "
            f"(stage={attempt.stage}, progress={attempt.progress})"
        )
        retried = _retry_or_fail(
            db,
            task=task,
            attempt=attempt,
            node=node,
            error=error,
            retryable=True,
        )
        if retried or task.status == "failed":
            recovered += 1
    db.flush()
    return recovered


def reap_expired_page_leases(db: Session) -> int:
    """Return expired page attempts to retry_wait, or fail after retry budget."""

    now = utcnow()
    tasks = db.scalars(
        select(RenderSubtask)
        .where(
            RenderSubtask.task_type == "page",
            RenderSubtask.status == "running",
            RenderSubtask.lease_expires_at.is_not(None),
            RenderSubtask.lease_expires_at <= now,
        )
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for task in tasks:
        attempt = db.get(RenderAttempt, task.active_attempt_id) if task.active_attempt_id else None
        node = db.get(WorkerNode, task.assigned_node_id) if task.assigned_node_id else None
        if attempt is None:
            task.status = "retry_wait"
            task.stage = "retry_wait"
            task.active_attempt_id = None
            task.assigned_node_id = None
            task.lease_expires_at = None
            task.available_at = now + timedelta(seconds=5)
            recovered += 1
            continue
        if node is None:
            # Keep accounting consistent even if an operator removed a node row.
            node = WorkerNode(
                id=attempt.node_id or secrets.token_hex(16),
                name="expired-worker",
                credential_hash=secrets.token_hex(32),
                status="offline",
                accepting_tasks=False,
                slots_total=1,
                slots_busy=1,
            )
        attempt.status = "expired"
        attempt.error = "worker lease expired"
        attempt.completed_at = now
        retried = _retry_or_fail(
            db,
            task=task,
            attempt=attempt,
            node=node,
            error="worker lease expired",
            retryable=True,
        )
        if retried or task.status == "failed":
            recovered += 1
    db.flush()
    return recovered
