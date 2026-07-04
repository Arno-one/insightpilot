"""新增 Memory Governance 状态表

Revision ID: 20260704_memory_governance
Revises: 20260704_memory_update_trace
Create Date: 2026-07-04 10:16:00
"""

from alembic import op


revision = "20260704_memory_governance"
down_revision = "20260704_memory_update_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_governance_state (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          governance_id VARCHAR(64) NOT NULL COMMENT '记忆治理状态业务主键',
          memory_id VARCHAR(64) NULL COMMENT '关联记忆 ID',
          customer_id VARCHAR(64) NOT NULL COMMENT '关联客户 ID',
          memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer' COMMENT '记忆范围',
          governance_status VARCHAR(30) NOT NULL DEFAULT 'enabled' COMMENT '治理状态：enabled / disabled',
          refresh_status VARCHAR(30) NOT NULL DEFAULT 'idle' COMMENT '刷新状态：idle / requested / running / completed / failed',
          reason VARCHAR(500) NULL COMMENT '治理动作原因',
          disabled_at DATETIME NULL COMMENT '禁用时间',
          disabled_by_user_id VARCHAR(64) NULL COMMENT '禁用操作人',
          refresh_requested_at DATETIME NULL COMMENT '刷新请求时间',
          refresh_requested_by_user_id VARCHAR(64) NULL COMMENT '刷新请求人',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_governance_id (governance_id),
          UNIQUE KEY uk_tenant_customer_scope (tenant_id, customer_id, memory_scope),
          KEY idx_tenant_status (tenant_id, governance_status),
          KEY idx_tenant_refresh_status (tenant_id, refresh_status),
          KEY idx_tenant_memory (tenant_id, memory_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Memory Governance 记忆治理状态表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_governance_state")
