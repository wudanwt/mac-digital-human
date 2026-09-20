"""Worker management metadata and heartbeat samples.

Revision ID: 0013_worker_management_metrics
Revises: 0012_auxiliary_task_leases
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_worker_management_metrics"
down_revision = "0012_auxiliary_task_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_nodes",
        sa.Column("group_name", sa.String(length=80), nullable=False, server_default="default"),
    )
    op.add_column(
        "worker_nodes",
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("worker_nodes", sa.Column("cpu_percent", sa.Float(), nullable=True))
    op.add_column("worker_nodes", sa.Column("memory_percent", sa.Float(), nullable=True))
    op.create_index("ix_worker_nodes_group_name", "worker_nodes", ["group_name"])

    op.create_table(
        "worker_heartbeat_samples",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "node_id",
            sa.String(length=32),
            sa.ForeignKey("worker_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
        sa.Column("slots_busy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_task_id", sa.String(length=32), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("memory_available_mb", sa.Integer(), nullable=True),
        sa.Column("disk_free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_worker_heartbeat_samples_node_id", "worker_heartbeat_samples", ["node_id"])
    op.create_index("ix_worker_heartbeat_samples_created_at", "worker_heartbeat_samples", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeat_samples_created_at", table_name="worker_heartbeat_samples")
    op.drop_index("ix_worker_heartbeat_samples_node_id", table_name="worker_heartbeat_samples")
    op.drop_table("worker_heartbeat_samples")

    op.drop_index("ix_worker_nodes_group_name", table_name="worker_nodes")
    op.drop_column("worker_nodes", "memory_percent")
    op.drop_column("worker_nodes", "cpu_percent")
    op.drop_column("worker_nodes", "notes")
    op.drop_column("worker_nodes", "group_name")
