"""为通知表补充邮件投递状态与重试字段
Revision ID: 20260703_notification_delivery
Revises: 20260703_tool_calling
Create Date: 2026-07-03 18:30:00
"""

from alembic import op
from sqlalchemy import text


revision = "20260703_notification_delivery"
down_revision = "20260703_tool_calling"
branch_labels = None
depends_on = None


def _has_column(column_name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text(
                """
                SELECT COUNT(1)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'internal_notification'
                  AND COLUMN_NAME = :column_name
                """
            ),
            {"column_name": column_name},
        ).scalar_one()
    )


def upgrade() -> None:
    alter_statements = {
        "delivery_status": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN delivery_status VARCHAR(30) NOT NULL DEFAULT 'pending' "
            "COMMENT '邮件投递状态，例如 pending / sent / failed / fallback_internal / skipped' AFTER read_at"
        ),
        "provider": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN provider VARCHAR(30) NULL COMMENT '外部投递提供方，例如 smtp' AFTER delivery_status"
        ),
        "provider_message_id": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN provider_message_id VARCHAR(128) NULL COMMENT '外部投递消息 ID' AFTER provider"
        ),
        "retry_count": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN retry_count INT NOT NULL DEFAULT 0 COMMENT '邮件投递累计尝试次数' AFTER provider_message_id"
        ),
        "last_attempted_at": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN last_attempted_at DATETIME NULL COMMENT '最近一次外部投递尝试时间' AFTER retry_count"
        ),
        "next_retry_at": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN next_retry_at DATETIME NULL COMMENT '建议下次重试时间' AFTER last_attempted_at"
        ),
        "last_error": (
            "ALTER TABLE internal_notification "
            "ADD COLUMN last_error TEXT NULL COMMENT '最近一次外部投递错误信息' AFTER next_retry_at"
        ),
    }
    for column_name, sql in alter_statements.items():
        if not _has_column(column_name):
            op.execute(sql)


def downgrade() -> None:
    drop_order = [
        "last_error",
        "next_retry_at",
        "last_attempted_at",
        "retry_count",
        "provider_message_id",
        "provider",
        "delivery_status",
    ]
    for column_name in drop_order:
        if _has_column(column_name):
            op.execute(f"ALTER TABLE internal_notification DROP COLUMN {column_name}")
