"""usage ledger idempotency

Revision ID: 0004_usage_idempotency
Revises: 0003_content_reports
Create Date: 2026-09-16
"""

from alembic import op

revision = "0004_usage_idempotency"
down_revision = "0003_content_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_usage_ledger_job_kind",
        "usage_ledger",
        ["job_id", "kind"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_usage_ledger_job_kind", table_name="usage_ledger")
