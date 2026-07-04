"""新增 Agent Definition 表

Revision ID: 20260704_agent_definition
Revises: 20260704_memory_governance
Create Date: 2026-07-04 10:17:00
"""

from alembic import op


revision = "20260704_agent_definition"
down_revision = "20260704_memory_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_definition (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          definition_id VARCHAR(64) NOT NULL COMMENT 'Agent Definition 业务主键',
          agent_code VARCHAR(80) NOT NULL COMMENT 'Agent 编码',
          agent_name VARCHAR(120) NOT NULL COMMENT 'Agent 名称',
          description TEXT NULL COMMENT 'Agent 描述',
          agent_type VARCHAR(50) NOT NULL DEFAULT 'custom' COMMENT 'Agent 类型',
          runtime_type VARCHAR(50) NOT NULL DEFAULT 'chat' COMMENT '运行时类型：chat / workflow / tool_agent',
          status VARCHAR(30) NOT NULL DEFAULT 'draft' COMMENT '状态：draft / active / disabled',
          version INT NOT NULL DEFAULT 1 COMMENT '定义版本号',
          config_json JSON NULL COMMENT 'Agent 基础配置 JSON',
          tool_policy_json JSON NULL COMMENT '工具策略 JSON',
          memory_policy_json JSON NULL COMMENT '记忆策略 JSON',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建人',
          updated_by_user_id VARCHAR(64) NOT NULL COMMENT '最近更新人',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_definition_id (definition_id),
          UNIQUE KEY uk_tenant_agent_version (tenant_id, agent_code, version),
          KEY idx_tenant_status_updated (tenant_id, status, updated_at),
          KEY idx_tenant_agent_code (tenant_id, agent_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent Studio Agent Definition 表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_definition")
