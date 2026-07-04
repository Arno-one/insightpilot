"""新增 Tool Evaluation 结果表

Revision ID: 20260704_tool_evaluation
Revises: 20260704_rag_evaluation
Create Date: 2026-07-04 10:13:00
"""

from alembic import op


revision = "20260704_tool_evaluation"
down_revision = "20260704_rag_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_evaluation_result (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          result_id VARCHAR(64) NOT NULL COMMENT 'Tool 评测结果业务主键',
          dataset_id VARCHAR(64) NOT NULL COMMENT '评测数据集 ID',
          case_id VARCHAR(64) NOT NULL COMMENT '评测样本 ID',
          tool_name VARCHAR(120) NOT NULL COMMENT '工具名称',
          run_id VARCHAR(64) NULL COMMENT '关联 Agent Run ID',
          step_id VARCHAR(64) NULL COMMENT '关联 Agent Step ID',
          status VARCHAR(30) NOT NULL COMMENT '执行状态：success / failed / skipped',
          expected_status VARCHAR(30) NOT NULL DEFAULT 'success' COMMENT '期望状态',
          failure_reason_category VARCHAR(80) NULL COMMENT '失败原因分类',
          failure_reason TEXT NULL COMMENT '失败原因详情',
          elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '工具执行耗时，毫秒',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_result_id (result_id),
          KEY idx_tenant_dataset_created (tenant_id, dataset_id, created_at),
          KEY idx_tenant_tool_created (tenant_id, tool_name, created_at),
          KEY idx_tenant_status_created (tenant_id, status, created_at),
          KEY idx_tenant_failure_category (tenant_id, failure_reason_category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tool Evaluation 结果表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tool_evaluation_result")
