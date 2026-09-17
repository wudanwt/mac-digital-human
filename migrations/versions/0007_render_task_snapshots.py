"""immutable render task snapshots

Revision ID: 0007_render_task_snapshots
Revises: 0006_speech_previews
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_render_task_snapshots"
down_revision = "0006_speech_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "render_task_snapshots",
        sa.Column(
            "job_id",
            sa.String(length=32),
            sa.ForeignKey("render_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=32),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_id", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_render_task_snapshots_tenant_id", "render_task_snapshots", ["tenant_id"])
    op.create_index("ix_render_task_snapshots_course_id", "render_task_snapshots", ["course_id"])
    op.create_index("ix_render_task_snapshots_snapshot_hash", "render_task_snapshots", ["snapshot_hash"])


def downgrade() -> None:
    op.drop_index("ix_render_task_snapshots_snapshot_hash", table_name="render_task_snapshots")
    op.drop_index("ix_render_task_snapshots_course_id", table_name="render_task_snapshots")
    op.drop_index("ix_render_task_snapshots_tenant_id", table_name="render_task_snapshots")
    op.drop_table("render_task_snapshots")
