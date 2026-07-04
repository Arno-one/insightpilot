"""新增 RAG Evaluation 结果表

Revision ID: 20260704_rag_evaluation
Revises: 20260704_nl2sql_evaluation
Create Date: 2026-07-04 10:12:00
"""

from alembic import op


revision = "20260704_rag_evaluation"
down_revision = "20260704_nl2sql_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_evaluation_result (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          result_id VARCHAR(64) NOT NULL COMMENT 'RAG 评测结果业务主键',
          dataset_id VARCHAR(64) NOT NULL COMMENT '评测数据集 ID',
          case_id VARCHAR(64) NOT NULL COMMENT '评测样本 ID',
          trace_id VARCHAR(64) NULL COMMENT '关联 RAG 检索 Trace ID',
          top_k INT NOT NULL DEFAULT 5 COMMENT '评测使用的 TopK',
          hit_count INT NOT NULL DEFAULT 0 COMMENT '当前样本命中的标准答案数量',
          expected_doc_id VARCHAR(128) NULL COMMENT '期望命中文档 ID',
          expected_section_id VARCHAR(128) NULL COMMENT '期望命中章节 ID',
          matched_rank INT NULL COMMENT '标准答案命中的排名，从 1 开始',
          recall_hit TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否在 TopK 内命中',
          mrr_score DECIMAL(10,6) NOT NULL DEFAULT 0 COMMENT '当前样本 MRR 得分',
          ndcg_score DECIMAL(10,6) NOT NULL DEFAULT 0 COMMENT '当前样本 NDCG 得分',
          rerank_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用重排',
          rerank_ms INT NOT NULL DEFAULT 0 COMMENT '重排耗时，毫秒',
          elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '评测耗时，毫秒',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_by_user_id VARCHAR(64) NOT NULL COMMENT '创建用户 ID',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_result_id (result_id),
          KEY idx_tenant_dataset_created (tenant_id, dataset_id, created_at),
          KEY idx_tenant_case_created (tenant_id, case_id, created_at),
          KEY idx_tenant_recall_created (tenant_id, recall_hit, created_at),
          KEY idx_tenant_trace (tenant_id, trace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='RAG Evaluation 结果表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag_evaluation_result")
