"""合并客户记忆与通知投递两条迁移分支
Revision ID: 20260703_merge_agent_platform
Revises: 20260703_customer_memory, 20260703_notification_delivery
Create Date: 2026-07-03 20:10:00
"""

revision = "20260703_merge_agent_platform"
down_revision = ("20260703_customer_memory", "20260703_notification_delivery")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
