"""SaaS hardening fields

Revision ID: 0002_saas_hardening
Revises: 0001_initial_saas
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_saas_hardening"
down_revision = "0001_initial_saas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("render_jobs", sa.Column("output_asset_id", sa.String(length=32), nullable=True))
    op.create_index("ix_render_jobs_output_asset_id", "render_jobs", ["output_asset_id"], unique=False)
    op.create_foreign_key(
        "fk_render_jobs_output_asset_id_assets",
        "render_jobs",
        "assets",
        ["output_asset_id"],
        ["id"],
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("consent_type", sa.String(length=60), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_records_tenant_id", "consent_records", ["tenant_id"], unique=False)
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"], unique=False)
    op.create_index("ix_consent_records_subject_type", "consent_records", ["subject_type"], unique=False)
    op.create_index("ix_consent_records_subject_id", "consent_records", ["subject_id"], unique=False)
    op.create_index("ix_consent_records_consent_type", "consent_records", ["consent_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_consent_records_consent_type", table_name="consent_records")
    op.drop_index("ix_consent_records_subject_id", table_name="consent_records")
    op.drop_index("ix_consent_records_subject_type", table_name="consent_records")
    op.drop_index("ix_consent_records_user_id", table_name="consent_records")
    op.drop_index("ix_consent_records_tenant_id", table_name="consent_records")
    op.drop_table("consent_records")

    op.drop_constraint("fk_render_jobs_output_asset_id_assets", "render_jobs", type_="foreignkey")
    op.drop_index("ix_render_jobs_output_asset_id", table_name="render_jobs")
    op.drop_column("render_jobs", "output_asset_id")
