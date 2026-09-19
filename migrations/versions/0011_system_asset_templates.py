"""Platform asset catalog and tenant imports.

Revision ID: 0011_system_asset_templates
Revises: 0010_merge_operations_worker
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_system_asset_templates"
down_revision = "0010_merge_operations_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_asset_templates",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "source_id", name="uq_system_asset_template_source"),
    )
    op.create_index("ix_system_asset_templates_kind", "system_asset_templates", ["kind"])
    op.create_table(
        "system_asset_imports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.String(32), sa.ForeignKey("system_asset_templates.id"), nullable=False),
        sa.Column("imported_id", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "template_id", name="uq_system_asset_import_tenant_template"),
    )
    op.create_index("ix_system_asset_imports_tenant_id", "system_asset_imports", ["tenant_id"])
    op.create_index("ix_system_asset_imports_template_id", "system_asset_imports", ["template_id"])


def downgrade() -> None:
    op.drop_table("system_asset_imports")
    op.drop_table("system_asset_templates")
