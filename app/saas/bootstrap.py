from __future__ import annotations

from sqlalchemy import select

from . import avatar_matting_models as _avatar_matting_models  # noqa: F401 - register Base metadata
from . import distributed_render_models as _distributed_render_models  # noqa: F401 - register Base metadata
from . import operations_models as _operations_models  # noqa: F401 - register Base metadata
from . import render_snapshot_models as _render_snapshot_models  # noqa: F401 - register Base metadata
from . import render_snapshot_service as _render_snapshot_service  # noqa: F401 - register snapshot capture hook
from . import distributed_graph_hook as _distributed_graph_hook  # noqa: F401 - initialize distributed task graph
from . import distributed_progress_hook as _distributed_progress_hook  # noqa: F401 - aggregate parent progress
from . import speech_preview_models as _speech_preview_models  # noqa: F401 - register Base metadata
from .background_themes import ensure_builtin_backgrounds
from .database import SessionLocal, create_all
from .models import Plan, User
from .settings import saas_settings


DEFAULT_PLANS = (
    dict(code="free", name="体验版", monthly_minutes=30, storage_gb=2, max_avatars=1, max_members=1, priority=0, price_cny=0),
    dict(code="pro", name="专业版", monthly_minutes=600, storage_gb=50, max_avatars=5, max_members=3, priority=10, price_cny=199),
    dict(code="business", name="企业版", monthly_minutes=3000, storage_gb=500, max_avatars=30, max_members=20, priority=50, price_cny=699),
)


def seed_plans() -> None:
    with SessionLocal() as db:
        for item in DEFAULT_PLANS:
            plan = db.get(Plan, item["code"])
            if plan is None:
                db.add(Plan(**item))
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
    ensure_builtin_backgrounds()
    if not saas_settings.is_production:
        saas_settings.storage_local_root.mkdir(parents=True, exist_ok=True)
        # SQLite remains convenient for direct local Python development. PostgreSQL,
        # including the Docker acceptance stack, is always managed by Alembic.
        if saas_settings.database_url.startswith("sqlite"):
            create_all()
    seed_plans()
    sync_superusers()


def main() -> None:
    initialize()
    print("SaaS runtime bootstrap completed.")


if __name__ == "__main__":
    main()
