"""新增 LLM 调用成本与 token 日志表

Revision ID: 20260704_llm_call_log
Revises: 20260704_agent_run_plan
Create Date: 2026-07-04 10:09:00
"""

from alembic import op


revision = "20260704_llm_call_log"
down_revision = "20260704_agent_run_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_call_log (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          call_id VARCHAR(64) NOT NULL COMMENT 'LLM 调用业务主键',
          user_id VARCHAR(64) NULL COMMENT '触发用户 ID',
          source VARCHAR(100) NOT NULL COMMENT '调用来源，例如 nl2sql.generate_sql / RiskAdvice',
          provider VARCHAR(50) NOT NULL DEFAULT 'deepseek' COMMENT '模型服务商',
          model VARCHAR(100) NOT NULL COMMENT '模型名称',
          status VARCHAR(30) NOT NULL DEFAULT 'success' COMMENT '调用状态：success / failed',
          prompt_tokens INT NOT NULL DEFAULT 0 COMMENT '输入 token 数',
          completion_tokens INT NOT NULL DEFAULT 0 COMMENT '输出 token 数',
          total_tokens INT NOT NULL DEFAULT 0 COMMENT '总 token 数',
          latency_ms INT NOT NULL DEFAULT 0 COMMENT '调用耗时，毫秒',
          estimated_cost DECIMAL(12, 6) NOT NULL DEFAULT 0.000000 COMMENT '预估成本金额，V1 默认保留字段',
          currency VARCHAR(10) NOT NULL DEFAULT 'USD' COMMENT '成本币种',
          error_message TEXT NULL COMMENT '失败错误信息',
          metadata_json JSON NULL COMMENT '调用扩展上下文 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_call_id (call_id),
          KEY idx_tenant_created (tenant_id, created_at),
          KEY idx_tenant_source_created (tenant_id, source, created_at),
          KEY idx_tenant_model_created (tenant_id, model, created_at),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='LLM 调用 token 与成本日志表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_call_log")
