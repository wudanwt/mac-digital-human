"""initial SaaS schema

Revision ID: 0001_initial_saas
Revises:
Create Date: 2026-09-15
"""

from alembic import op

from app.saas.database import Base
from app.saas import models  # noqa: F401

revision = "0001_initial_saas"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
