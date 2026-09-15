"""content report workflow

Revision ID: 0003_content_reports
Revises: 0002_saas_hardening
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_content_reports"
down_revision = "0002_saas_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_reports",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_reports_tenant_id", "content_reports", ["tenant_id"], unique=False)
    op.create_index("ix_content_reports_user_id", "content_reports", ["user_id"], unique=False)
    op.create_index("ix_content_reports_target_type", "content_reports", ["target_type"], unique=False)
    op.create_index("ix_content_reports_target_id", "content_reports", ["target_id"], unique=False)
    op.create_index("ix_content_reports_reason", "content_reports", ["reason"], unique=False)
    op.create_index("ix_content_reports_status", "content_reports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_reports_status", table_name="content_reports")
    op.drop_index("ix_content_reports_reason", table_name="content_reports")
    op.drop_index("ix_content_reports_target_id", table_name="content_reports")
    op.drop_index("ix_content_reports_target_type", table_name="content_reports")
    op.drop_index("ix_content_reports_user_id", table_name="content_reports")
    op.drop_index("ix_content_reports_tenant_id", table_name="content_reports")
    op.drop_table("content_reports")
