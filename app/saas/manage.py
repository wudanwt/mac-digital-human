from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from .database import SessionLocal
from .models import Membership, Tenant, User
from .security import hash_password
from .services import active_subscription, unique_slug


def create_admin(email: str, display_name: str, workspace_name: str) -> None:
    email = email.lower().strip()
    password = getpass.getpass("Admin password: ")
    password2 = getpass.getpass("Confirm password: ")
    if password != password2:
        raise SystemExit("Passwords do not match")

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

        membership = db.scalar(select(Membership).where(Membership.user_id == user.id).limit(1))
        if membership is None:
            tenant = Tenant(
                name=workspace_name.strip() or "平台管理",
                slug=unique_slug(db, workspace_name or "platform-admin"),
                owner_user_id=user.id,
            )
            db.add(tenant)
            db.flush()
            membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
            db.add(membership)
            db.flush()
            active_subscription(db, tenant.id, initial_seconds=0)
        db.commit()
    print(f"Administrator ready: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SaaS administration helpers")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="create or promote a platform administrator")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Platform Admin")
    create.add_argument("--workspace", default="平台管理")
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.name, args.workspace)


if __name__ == "__main__":
    main()
