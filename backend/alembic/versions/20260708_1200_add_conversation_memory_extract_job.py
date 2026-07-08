"""新增对话长期事实抽取任务表

Revision ID: 20260708_conversation_memory_extract_job
Revises: 20260708_customer_memory_atomic
Create Date: 2026-07-08 12:00:00
"""

from alembic import op


revision = "20260708_conversation_memory_extract_job"
down_revision = "20260708_customer_memory_atomic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_memory_extract_job (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          extract_job_id VARCHAR(64) NOT NULL COMMENT '长期事实抽取任务业务主键',
          customer_id VARCHAR(64) NOT NULL COMMENT '关联客户 ID',
          user_id VARCHAR(64) NOT NULL COMMENT '触发抽取的用户 ID',
          source_type VARCHAR(30) NOT NULL DEFAULT 'risk_chat' COMMENT '来源会话类型',
          session_key VARCHAR(191) NOT NULL COMMENT '来源会话键',
          status VARCHAR(30) NOT NULL DEFAULT 'queued' COMMENT '任务状态：queued / running / success / failed',
          trigger_message_count INT NOT NULL DEFAULT 0 COMMENT '本次触发的消息数',
          trigger_batch_json JSON NULL COMMENT '本次触发消息窗口 JSON',
          recent_window_json JSON NULL COMMENT '近期会话窗口 JSON',
          history_summary TEXT NULL COMMENT '触发时的历史摘要',
          queued_job_id VARCHAR(64) NULL COMMENT 'RQ 队列任务 ID',
          extracted_facts_json JSON NULL COMMENT '抽取出的长期事实 JSON',
          error_message TEXT NULL COMMENT '失败原因',
          started_at DATETIME NULL COMMENT '开始执行时间',
          finished_at DATETIME NULL COMMENT '执行完成时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_extract_job_id (extract_job_id),
          KEY idx_tenant_customer_status (tenant_id, customer_id, status),
          KEY idx_tenant_user_created (tenant_id, user_id, created_at),
          KEY idx_tenant_session_created (tenant_id, session_key, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对话长期事实抽取任务表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation_memory_extract_job")
