"""course speech preview jobs

Revision ID: 0006_speech_previews
Revises: 0005_avatar_matting
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_speech_previews"
down_revision = "0005_avatar_matting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "speech_preview_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(length=32), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_profile_id", sa.String(length=32), sa.ForeignKey("voice_profiles.id"), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="queued"),
        sa.Column("audio_asset_id", sa.String(length=32), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("tenant_id", "user_id", "course_id", "voice_profile_id", "text_hash", "status"):
        op.create_index(f"ix_speech_preview_jobs_{column}", "speech_preview_jobs", [column])


def downgrade() -> None:
    for column in ("status", "text_hash", "voice_profile_id", "course_id", "user_id", "tenant_id"):
        op.drop_index(f"ix_speech_preview_jobs_{column}", table_name="speech_preview_jobs")
    op.drop_table("speech_preview_jobs")
