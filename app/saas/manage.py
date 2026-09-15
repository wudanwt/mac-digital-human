from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from .database import SessionLocal
from .models import Membership, Tenant, User
from .security import hash_password
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

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.name, args.workspace)
    elif args.command == "create-user":
        create_user(args.email, args.name, args.workspace, args.free_trial)


if __name__ == "__main__":
    main()
