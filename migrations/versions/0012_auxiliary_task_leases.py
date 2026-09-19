"""Lease remote portrait matting and speech preview jobs.

Revision ID: 0012_auxiliary_task_leases
Revises: 0011_system_asset_templates
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_auxiliary_task_leases"
down_revision = "0011_system_asset_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auxiliary_task_leases",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("job_id", sa.String(32), nullable=False),
        sa.Column("node_id", sa.String(32), sa.ForeignKey("worker_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "job_id", name="uq_auxiliary_task_job"),
    )
    op.create_index("ix_auxiliary_task_leases_expires_at", "auxiliary_task_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auxiliary_task_leases")
