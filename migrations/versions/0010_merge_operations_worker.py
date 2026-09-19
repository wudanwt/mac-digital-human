"""merge operations management and worker enrollment migration heads

Revision ID: 0010_merge_operations_worker
Revises: 0009_operations_management, 0009_worker_enrollment
Create Date: 2026-09-19
"""

revision = "0010_merge_operations_worker"
down_revision = ("0009_operations_management", "0009_worker_enrollment")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
