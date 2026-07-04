"""新增 Memory Update Trace 表

Revision ID: 20260704_memory_update_trace
Revises: 20260704_agent_evaluation
Create Date: 2026-07-04 10:15:00
"""

from alembic import op


revision = "20260704_memory_update_trace"
down_revision = "20260704_agent_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_update_trace (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          trace_id VARCHAR(64) NOT NULL COMMENT '记忆更新轨迹业务主键',
          memory_id VARCHAR(64) NOT NULL COMMENT '关联记忆 ID',
          customer_id VARCHAR(64) NOT NULL COMMENT '关联客户 ID',
          memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer' COMMENT '记忆范围',
          update_type VARCHAR(30) NOT NULL COMMENT '更新类型：create / update',
          source_type VARCHAR(50) NOT NULL COMMENT '更新来源类型，例如 agent_run / manual',
          source_run_id VARCHAR(64) NULL COMMENT '来源 Agent Run ID',
          changed_fields_json JSON NULL COMMENT '变更字段列表 JSON',
          summary_preview TEXT NULL COMMENT '更新后的摘要预览',
          profile_tags_json JSON NULL COMMENT '更新后的画像标签 JSON',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_trace_id (trace_id),
          KEY idx_tenant_customer_created (tenant_id, customer_id, created_at),
          KEY idx_tenant_memory_created (tenant_id, memory_id, created_at),
          KEY idx_tenant_source_run (tenant_id, source_run_id),
          KEY idx_tenant_update_type (tenant_id, update_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Memory Update Trace 记忆更新轨迹表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_update_trace")
