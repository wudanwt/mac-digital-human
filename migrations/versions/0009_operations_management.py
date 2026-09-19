"""operations management subscription history

Revision ID: 0009_operations_management
Revises: 0008_distributed_render_control_plane
Create Date: 2026-09-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_operations_management"
down_revision = "0008_distributed_render_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_periods",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("subscription_id", sa.String(length=32), nullable=False),
        sa.Column("plan_code", sa.String(length=40), nullable=False),
        sa.Column("source_order_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("activation_mode", sa.String(length=32), nullable=False),
        sa.Column("granted_seconds", sa.Integer(), nullable=False),
        sa.Column("amount_cny", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_code"], ["plans.code"]),
        sa.ForeignKeyConstraint(["source_order_id"], ["payment_orders.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscription_periods_tenant_id", "subscription_periods", ["tenant_id"])
    op.create_index("ix_subscription_periods_subscription_id", "subscription_periods", ["subscription_id"])
    op.create_index("ix_subscription_periods_plan_code", "subscription_periods", ["plan_code"])
    op.create_index("ix_subscription_periods_source_order_id", "subscription_periods", ["source_order_id"])
    op.create_index("ix_subscription_periods_status", "subscription_periods", ["status"])
    op.create_index("ix_subscription_periods_created_by_user_id", "subscription_periods", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("subscription_periods")
