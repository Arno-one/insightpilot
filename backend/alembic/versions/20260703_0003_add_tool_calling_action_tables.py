"""新增 Tool Calling 动作闭环相关表

Revision ID: 20260703_0003
Revises: 20260702_0002
Create Date: 2026-07-03 14:30:00
"""

from alembic import op


revision = "20260703_0003"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_notification (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          notification_id VARCHAR(64) NOT NULL COMMENT '通知业务主键',
          task_id VARCHAR(64) NOT NULL COMMENT '关联任务 ID',
          approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
          customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
          recipient_user_id VARCHAR(64) NOT NULL COMMENT '接收人用户 ID',
          sender_user_id VARCHAR(64) NOT NULL COMMENT '发送人用户 ID',
          notification_type VARCHAR(50) NOT NULL COMMENT '通知类型，例如 task_assignment',
          channel VARCHAR(30) NOT NULL DEFAULT 'internal' COMMENT '通知通道，例如 internal / wecom / email',
          title VARCHAR(150) NOT NULL COMMENT '通知标题',
          content TEXT NOT NULL COMMENT '通知正文',
          status VARCHAR(30) NOT NULL DEFAULT 'sent' COMMENT '通知状态，例如 sent / failed / read',
          delivered_at DATETIME NULL COMMENT '送达时间',
          read_at DATETIME NULL COMMENT '阅读时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_notification_id (notification_id),
          UNIQUE KEY uk_task_recipient_type (tenant_id, task_id, recipient_user_id, notification_type),
          KEY idx_tenant_recipient_status (tenant_id, recipient_user_id, status),
          KEY idx_tenant_task (tenant_id, task_id),
          KEY idx_tenant_customer (tenant_id, customer_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台内通知记录表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_calendar_event (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          event_id VARCHAR(64) NOT NULL COMMENT '日程业务主键',
          task_id VARCHAR(64) NOT NULL COMMENT '关联任务 ID',
          approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
          customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
          owner_user_id VARCHAR(64) NOT NULL COMMENT '日程负责人用户 ID',
          title VARCHAR(150) NOT NULL COMMENT '日程标题',
          description TEXT NULL COMMENT '日程说明',
          start_at DATETIME NOT NULL COMMENT '开始时间',
          end_at DATETIME NOT NULL COMMENT '结束时间',
          status VARCHAR(30) NOT NULL DEFAULT 'scheduled' COMMENT '日程状态，例如 scheduled / done / cancelled',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建人用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_event_id (event_id),
          UNIQUE KEY uk_task_owner (tenant_id, task_id, owner_user_id),
          KEY idx_tenant_owner_start (tenant_id, owner_user_id, start_at),
          KEY idx_tenant_task (tenant_id, task_id),
          KEY idx_tenant_customer (tenant_id, customer_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台内日程记录表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS internal_calendar_event")
    op.execute("DROP TABLE IF EXISTS internal_notification")
