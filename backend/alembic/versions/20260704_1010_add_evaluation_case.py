"""新增 Evaluation Case 评测样本结构

Revision ID: 20260704_evaluation_case
Revises: 20260704_llm_call_log
Create Date: 2026-07-04 10:10:00
"""

from alembic import op


revision = "20260704_evaluation_case"
down_revision = "20260704_llm_call_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_dataset (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          dataset_id VARCHAR(64) NOT NULL COMMENT '评测数据集业务主键',
          name VARCHAR(120) NOT NULL COMMENT '数据集名称',
          description TEXT NULL COMMENT '数据集说明',
          target_type VARCHAR(40) NOT NULL COMMENT '绑定目标类型：agent / tool / rag / nl2sql',
          status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '状态：active / archived',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_dataset_id (dataset_id),
          KEY idx_tenant_target (tenant_id, target_type),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Evaluation 评测数据集表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_case (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          case_id VARCHAR(64) NOT NULL COMMENT '评测样本业务主键',
          dataset_id VARCHAR(64) NOT NULL COMMENT '所属评测数据集 ID',
          title VARCHAR(160) NOT NULL COMMENT '样本标题',
          user_input TEXT NOT NULL COMMENT '评测输入或用户问题',
          expected_behavior TEXT NOT NULL COMMENT '期望行为或验收标准',
          target_type VARCHAR(40) NOT NULL COMMENT '绑定目标类型：agent / tool / rag / nl2sql',
          target_name VARCHAR(120) NOT NULL COMMENT '绑定目标名称',
          tags_json JSON NULL COMMENT '标签数组 JSON',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '状态：active / archived',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_case_id (case_id),
          KEY idx_tenant_dataset (tenant_id, dataset_id),
          KEY idx_tenant_target (tenant_id, target_type, target_name),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Evaluation 评测样本表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_case")
    op.execute("DROP TABLE IF EXISTS evaluation_dataset")
