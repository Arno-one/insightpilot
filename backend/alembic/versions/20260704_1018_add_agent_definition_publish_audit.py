"""新增 Agent Definition 发布审计表

Revision ID: 20260704_agent_publish_audit
Revises: 20260704_agent_definition
Create Date: 2026-07-04 10:18:00
"""

from alembic import op


revision = "20260704_agent_publish_audit"
down_revision = "20260704_agent_definition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_definition_publish_audit (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          audit_id VARCHAR(64) NOT NULL COMMENT '发布审计业务主键',
          definition_id VARCHAR(64) NOT NULL COMMENT 'Agent Definition 业务主键',
          agent_code VARCHAR(80) NOT NULL COMMENT 'Agent 编码',
          version INT NOT NULL COMMENT 'Agent Definition 版本号',
          publish_status VARCHAR(30) NOT NULL COMMENT '发布结果：published / blocked',
          validation_json JSON NULL COMMENT '发布门禁校验结果 JSON',
          error_count INT NOT NULL DEFAULT 0 COMMENT '错误数量',
          warning_count INT NOT NULL DEFAULT 0 COMMENT '警告数量',
          message VARCHAR(500) NULL COMMENT '发布结果说明',
          published_by_user_id VARCHAR(64) NOT NULL COMMENT '发布操作人',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '审计创建时间',
          UNIQUE KEY uk_agent_publish_audit_id (audit_id),
          KEY idx_tenant_definition_created (tenant_id, definition_id, created_at),
          KEY idx_tenant_agent_created (tenant_id, agent_code, created_at),
          KEY idx_tenant_status_created (tenant_id, publish_status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent Definition 发布门禁审计表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_definition_publish_audit")
