"""avatar transparent asset processing

Revision ID: 0005_avatar_matting
Revises: 0004_usage_idempotency
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_avatar_matting"
down_revision = "0004_usage_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "avatar_matting_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("avatar_id", sa.String(length=32), sa.ForeignKey("avatars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_asset_id", sa.String(length=32), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="queued"),
        sa.Column("model", sa.String(length=120), nullable=False, server_default="birefnet-portrait"),
        sa.Column("alpha_asset_id", sa.String(length=32), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("poster_asset_id", sa.String(length=32), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("white_preview_asset_id", sa.String(length=32), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_avatar_matting_jobs_tenant_id", "avatar_matting_jobs", ["tenant_id"])
    op.create_index("ix_avatar_matting_jobs_user_id", "avatar_matting_jobs", ["user_id"])
    op.create_index("ix_avatar_matting_jobs_avatar_id", "avatar_matting_jobs", ["avatar_id"])
    op.create_index("ix_avatar_matting_jobs_source_asset_id", "avatar_matting_jobs", ["source_asset_id"])
    op.create_index("ix_avatar_matting_jobs_status", "avatar_matting_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_avatar_matting_jobs_status", table_name="avatar_matting_jobs")
    op.drop_index("ix_avatar_matting_jobs_source_asset_id", table_name="avatar_matting_jobs")
    op.drop_index("ix_avatar_matting_jobs_avatar_id", table_name="avatar_matting_jobs")
    op.drop_index("ix_avatar_matting_jobs_user_id", table_name="avatar_matting_jobs")
    op.drop_index("ix_avatar_matting_jobs_tenant_id", table_name="avatar_matting_jobs")
    op.drop_table("avatar_matting_jobs")
