"""新增客户记忆表

Revision ID: 20260703_0003
Revises: 20260702_0002
Create Date: 2026-07-03 10:30:00
"""

from alembic import op


revision = "20260703_0003"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_memory (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          memory_id VARCHAR(64) NOT NULL COMMENT '客户记忆业务主键',
          customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
          memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer' COMMENT '记忆范围，V1 固定为 customer',
          summary_text TEXT NOT NULL COMMENT '供 Planner / Reviewer 直接消费的压缩记忆摘要',
          summary_json JSON NULL COMMENT '结构化客户记忆 JSON',
          source_run_id VARCHAR(64) NULL COMMENT '最近一次刷新该记忆的 Agent Run ID',
          last_compiled_at DATETIME NOT NULL COMMENT '最近一次编译客户记忆的时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_memory_id (memory_id),
          UNIQUE KEY uk_tenant_customer_scope (tenant_id, customer_id, memory_scope),
          KEY idx_tenant_customer (tenant_id, customer_id),
          KEY idx_tenant_compiled_at (tenant_id, last_compiled_at),
          KEY idx_source_run_id (source_run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户长期记忆表，V1 先服务风险 Agent'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customer_memory")
