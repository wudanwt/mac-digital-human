"""distributed render control plane

Revision ID: 0008_distributed_render_control_plane
Revises: 0007_render_task_snapshots
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_distributed_render_control_plane"
down_revision = "0007_render_task_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_nodes",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("credential_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
        sa.Column("accepting_tasks", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("slots_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("slots_busy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("platform", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("machine", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("versions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("code_version", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("render_contract_version", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("current_task_id", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("disk_free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_available_mb", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("credential_hash", name="uq_worker_nodes_credential_hash"),
    )
    for column in ("status", "accepting_tasks", "current_task_id", "last_seen_at"):
        op.create_index(f"ix_worker_nodes_{column}", "worker_nodes", [column])

    op.create_table(
        "render_subtasks",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_job_id", sa.String(length=32), sa.ForeignKey("render_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(length=24), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="blocked"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_seconds", sa.Float(), nullable=True),
        sa.Column("assigned_node_id", sa.String(length=32), sa.ForeignKey("worker_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active_attempt_id", sa.String(length=32), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="blocked"),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("parent_job_id", "task_type", "slide_index", name="uq_render_subtask_parent_type_slide"),
    )
    for column in (
        "tenant_id", "parent_job_id", "task_type", "config_hash", "status", "priority",
        "assigned_node_id", "active_attempt_id", "lease_expires_at", "available_at",
    ):
        op.create_index(f"ix_render_subtasks_{column}", "render_subtasks", [column])
    op.create_index(
        "ix_render_subtasks_claim",
        "render_subtasks",
        ["status", "priority", "available_at", "created_at"],
    )

    op.create_table(
        "render_attempts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("subtask_id", sa.String(length=32), sa.ForeignKey("render_subtasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(length=32), sa.ForeignKey("worker_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("lease_token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="claimed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("subtask_id", "attempt_no", name="uq_render_attempt_subtask_number"),
    )
    for column in ("subtask_id", "node_id", "status", "lease_expires_at"):
        op.create_index(f"ix_render_attempts_{column}", "render_attempts", [column])

    op.create_table(
        "render_artifacts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tenant_id", sa.String(length=32), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_job_id", sa.String(length=32), sa.ForeignKey("render_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subtask_id", sa.String(length=32), sa.ForeignKey("render_subtasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("attempt_id", sa.String(length=32), sa.ForeignKey("render_attempts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("slide_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("object_key", sa.String(length=900), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=160), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("attempt_id", "kind", name="uq_render_artifact_attempt_kind"),
    )
    for column in (
        "tenant_id", "parent_job_id", "subtask_id", "attempt_id", "kind", "slide_index",
        "sha256", "status", "expires_at",
    ):
        op.create_index(f"ix_render_artifacts_{column}", "render_artifacts", [column])


def downgrade() -> None:
    for column in (
        "expires_at", "status", "sha256", "slide_index", "kind", "attempt_id", "subtask_id",
        "parent_job_id", "tenant_id",
    ):
        op.drop_index(f"ix_render_artifacts_{column}", table_name="render_artifacts")
    op.drop_table("render_artifacts")

    for column in ("lease_expires_at", "status", "node_id", "subtask_id"):
        op.drop_index(f"ix_render_attempts_{column}", table_name="render_attempts")
    op.drop_table("render_attempts")

    op.drop_index("ix_render_subtasks_claim", table_name="render_subtasks")
    for column in (
        "available_at", "lease_expires_at", "active_attempt_id", "assigned_node_id", "priority",
        "status", "config_hash", "task_type", "parent_job_id", "tenant_id",
    ):
        op.drop_index(f"ix_render_subtasks_{column}", table_name="render_subtasks")
    op.drop_table("render_subtasks")

    for column in ("last_seen_at", "current_task_id", "accepting_tasks", "status"):
        op.drop_index(f"ix_worker_nodes_{column}", table_name="worker_nodes")
    op.drop_table("worker_nodes")
