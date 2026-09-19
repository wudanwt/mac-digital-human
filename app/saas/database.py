from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import saas_settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if saas_settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    saas_settings.database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    # Developer convenience only; production uses Alembic.
    from . import (  # noqa: F401
        auxiliary_task_models,
        compliance_models,
        distributed_render_models,
        models,
        render_snapshot_models,
        speech_preview_models,
    )

    Base.metadata.create_all(bind=engine)
