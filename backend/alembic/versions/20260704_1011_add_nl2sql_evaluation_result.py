"""新增 NL2SQL Evaluation 结果表

Revision ID: 20260704_nl2sql_evaluation
Revises: 20260704_evaluation_case
Create Date: 2026-07-04 10:11:00
"""

from alembic import op


revision = "20260704_nl2sql_evaluation"
down_revision = "20260704_evaluation_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nl2sql_evaluation_result (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          result_id VARCHAR(64) NOT NULL COMMENT '评测结果业务主键',
          dataset_id VARCHAR(64) NOT NULL COMMENT '评测数据集 ID',
          case_id VARCHAR(64) NOT NULL COMMENT '评测样本 ID',
          query_id VARCHAR(64) NULL COMMENT '关联 NL2SQL 查询审计 ID',
          generated_sql TEXT NULL COMMENT '生成或待评测 SQL',
          status VARCHAR(30) NOT NULL COMMENT '结果状态：executed / failed',
          row_count INT NOT NULL DEFAULT 0 COMMENT '执行返回行数',
          error_message TEXT NULL COMMENT '错误信息',
          elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '评测耗时，毫秒',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_result_id (result_id),
          KEY idx_tenant_dataset_created (tenant_id, dataset_id, created_at),
          KEY idx_tenant_case_created (tenant_id, case_id, created_at),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NL2SQL Evaluation 结果表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl2sql_evaluation_result")
