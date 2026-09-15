from __future__ import annotations

from sqlalchemy import select

from .database import SessionLocal, create_all
from .models import Plan, User
from .settings import saas_settings


DEFAULT_PLANS = (
    dict(code="free", name="体验版", monthly_minutes=30, storage_gb=2, max_avatars=1, max_members=1, priority=0, price_cny=0),
    dict(code="pro", name="专业版", monthly_minutes=600, storage_gb=50, max_avatars=5, max_members=3, priority=10, price_cny=199),
    dict(code="business", name="企业版", monthly_minutes=3000, storage_gb=500, max_avatars=30, max_members=20, priority=20, price_cny=699),
)


def seed_plans() -> None:
    with SessionLocal() as db:
        for item in DEFAULT_PLANS:
            plan = db.get(Plan, item["code"])
            if plan is None:
                db.add(Plan(**item))
            else:
                for key, value in item.items():
                    setattr(plan, key, value)
        db.commit()


def sync_superusers() -> None:
    if not saas_settings.admin_emails:
        return
    wanted = {e.lower() for e in saas_settings.admin_emails}
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        changed = False
        for user in users:
            should = user.email.lower() in wanted
            if user.is_superuser != should:
                user.is_superuser = should
                changed = True
        if changed:
            db.commit()


def initialize() -> None:
    saas_settings.validate_production()
    saas_settings.storage_local_root.mkdir(parents=True, exist_ok=True)
    create_all()
    seed_plans()
    sync_superusers()


def main() -> None:
    initialize()
    print("SaaS database initialized.")


if __name__ == "__main__":
    main()
