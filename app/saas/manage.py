from __future__ import annotations

import argparse
import getpass
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from .database import SessionLocal
from .distributed_render_models import WorkerEnrollment, WorkerNode
from .distributed_scheduler import hash_secret
from .models import Membership, Tenant, User
from .security import hash_password
from .settings import saas_settings
from .services import active_subscription, unique_slug


def _prompt_password(label: str = "Password") -> str:
    password = getpass.getpass(f"{label}: ")
    password2 = getpass.getpass(f"Confirm {label.lower()}: ")
    if password != password2:
        raise SystemExit("Passwords do not match")
    return password


def _ensure_workspace(db, user: User, workspace_name: str, *, free_trial: bool) -> Tenant:
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id).limit(1))
    if membership is not None:
        tenant = db.get(Tenant, membership.tenant_id)
        if tenant is None:
            raise SystemExit("Existing workspace membership is inconsistent")
        return tenant
    tenant = Tenant(
        name=workspace_name.strip() or "我的工作区",
        slug=unique_slug(db, workspace_name or "workspace"),
        owner_user_id=user.id,
    )
    db.add(tenant)
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
    db.flush()
    active_subscription(db, tenant.id, initial_seconds=None if free_trial else 0)
    return tenant


def create_admin(email: str, display_name: str, workspace_name: str) -> None:
    email = email.lower().strip()
    password = _prompt_password("Admin password")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=display_name.strip() or email.split("@", 1)[0],
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            user.is_superuser = True
        _ensure_workspace(db, user, workspace_name, free_trial=False)
        db.commit()
    print(f"Administrator ready: {email}")


def create_user(email: str, display_name: str, workspace_name: str, free_trial: bool) -> None:
    email = email.lower().strip()
    password = _prompt_password("Initial password")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("User already exists")
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name.strip() or email.split("@", 1)[0],
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        tenant = _ensure_workspace(db, user, workspace_name, free_trial=free_trial)
        db.commit()
    print(f"User ready: {email} / workspace={tenant.name} / free_trial={free_trial}")


def create_worker_enrollment(name: str, slots: int) -> None:
    """Provision a pending Worker and print a short-lived one-time enrollment code."""

    clean_name = name.strip()
    if not clean_name:
        raise SystemExit("Worker name cannot be empty")
    slots = max(1, min(4, int(slots)))
    node_id = uuid4().hex
    enrollment_id = uuid4().hex
    code = f"enr_{enrollment_id}_{secrets.token_urlsafe(24)}"
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(
        minutes=max(5, min(1440, saas_settings.distributed_enrollment_minutes))
    )
    with SessionLocal() as db:
        node = WorkerNode(
            id=node_id,
            name=clean_name,
            credential_hash=hash_secret(f"pending:{node_id}:{secrets.token_urlsafe(32)}"),
            status="pending",
            accepting_tasks=False,
            slots_total=slots,
            slots_busy=0,
            render_contract_version="",
        )
        enrollment = WorkerEnrollment(
            id=enrollment_id,
            node_id=node_id,
            token_hash=hash_secret(code),
            expires_at=expires_at,
            used_at=None,
        )
        db.add(node)
        db.flush()
        db.add(enrollment)
        db.commit()
    print(f"Pending Worker: {clean_name} / id={node_id} / slots={slots}")
    print(f"Enrollment expires: {expires_at.isoformat()}")
    print("REMOTE_WORKER_ENROLLMENT_CODE=" + code)
    print("The code is single-use. The long-lived Worker credential will be stored on the Mac after enrollment.")


def create_worker(name: str, slots: int) -> None:
    """Provision one revocable API-only compute worker credential.

    The plaintext token is printed once and only its SHA-256 digest is stored.
    Copy the token to that Mac's .env.remote-worker and do not commit it.
    """

    clean_name = name.strip()
    if not clean_name:
        raise SystemExit("Worker name cannot be empty")
    slots = max(1, min(4, int(slots)))
    node_id = uuid4().hex
    token = f"wrk_{node_id}_{secrets.token_urlsafe(32)}"
    with SessionLocal() as db:
        node = WorkerNode(
            id=node_id,
            name=clean_name,
            credential_hash=hash_secret(token),
            status="offline",
            accepting_tasks=True,
            slots_total=slots,
            slots_busy=0,
            render_contract_version="",
        )
        db.add(node)
        db.commit()
    print(f"Worker ready: {clean_name} / id={node_id} / slots={slots}")
    print("REMOTE_WORKER_TOKEN=" + token)
    print("Save this token now; the plaintext value is not stored by the center.")


def main() -> None:
    parser = argparse.ArgumentParser(description="SaaS administration helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="create or promote a platform administrator")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Platform Admin")
    create.add_argument("--workspace", default="平台管理")

    user = sub.add_parser("create-user", help="provision an invite-only SaaS user")
    user.add_argument("--email", required=True)
    user.add_argument("--name", default="")
    user.add_argument("--workspace", default="我的工作区")
    user.add_argument("--free-trial", action="store_true")

    worker = sub.add_parser("create-worker", help="provision an API-only distributed render worker")
    worker.add_argument("--name", required=True)
    worker.add_argument("--slots", type=int, default=1)

    enrollment = sub.add_parser(
        "create-worker-enrollment",
        help="provision a pending remote Worker and print a one-time enrollment code",
    )
    enrollment.add_argument("--name", required=True)
    enrollment.add_argument("--slots", type=int, default=1)

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.name, args.workspace)
    elif args.command == "create-user":
        create_user(args.email, args.name, args.workspace, args.free_trial)
    elif args.command == "create-worker":
        create_worker(args.name, args.slots)
    elif args.command == "create-worker-enrollment":
        create_worker_enrollment(args.name, args.slots)


if __name__ == "__main__":
    main()
