"""remote worker enrollment

Revision ID: 0009_worker_enrollment
Revises: 0008_distributed_render
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_worker_enrollment"
down_revision = "0008_distributed_render"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_enrollments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "node_id",
            sa.String(length=32),
            sa.ForeignKey("worker_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_worker_enrollments_token_hash"),
    )
    op.create_index("ix_worker_enrollments_node_id", "worker_enrollments", ["node_id"])
    op.create_index("ix_worker_enrollments_expires_at", "worker_enrollments", ["expires_at"])
    op.create_index("ix_worker_enrollments_used_at", "worker_enrollments", ["used_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_enrollments_used_at", table_name="worker_enrollments")
    op.drop_index("ix_worker_enrollments_expires_at", table_name="worker_enrollments")
    op.drop_index("ix_worker_enrollments_node_id", table_name="worker_enrollments")
    op.drop_table("worker_enrollments")
