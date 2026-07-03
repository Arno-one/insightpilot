"""新增动作链运行与步骤明细表
Revision ID: 20260703_action_chain_runtime
Revises: 20260703_merge_agent_platform
Create Date: 2026-07-03 23:10:00
"""

from alembic import op


revision = "20260703_action_chain_runtime"
down_revision = "20260703_merge_agent_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_action_run (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          action_run_id VARCHAR(64) NOT NULL COMMENT '动作链运行业务主键',
          chain_code VARCHAR(64) NOT NULL COMMENT '动作链编码',
          approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
          customer_id VARCHAR(64) NULL COMMENT '关联客户 ID',
          trigger_source VARCHAR(50) NOT NULL DEFAULT 'approval' COMMENT '触发来源，如 approval',
          triggered_by_user_id VARCHAR(64) NOT NULL COMMENT '触发动作链的用户 ID',
          status VARCHAR(30) NOT NULL DEFAULT 'running' COMMENT '动作链状态，如 running / success / failed',
          current_step_code VARCHAR(64) NULL COMMENT '当前步骤编码',
          context_payload_json JSON NULL COMMENT '动作链运行上下文快照',
          error_message TEXT NULL COMMENT '最近一次失败错误信息',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          finished_at DATETIME NULL COMMENT '最后一次完成或失败时间',
          UNIQUE KEY uk_action_run_id (action_run_id),
          KEY idx_tenant_status_created (tenant_id, status, created_at),
          KEY idx_tenant_approval_created (tenant_id, approval_id, created_at),
          KEY idx_tenant_customer_created (tenant_id, customer_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审批后动作链运行表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_action_run_step (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          step_run_id VARCHAR(64) NOT NULL COMMENT '步骤运行业务主键',
          action_run_id VARCHAR(64) NOT NULL COMMENT '所属动作链运行 ID',
          approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
          customer_id VARCHAR(64) NULL COMMENT '关联客户 ID',
          step_code VARCHAR(64) NOT NULL COMMENT '步骤编码',
          tool_name VARCHAR(120) NOT NULL COMMENT '执行的工具名',
          step_order INT NOT NULL COMMENT '步骤顺序',
          status VARCHAR(30) NOT NULL DEFAULT 'running' COMMENT '步骤状态，如 running / success / failed',
          input_payload_json JSON NULL COMMENT '步骤输入快照',
          output_payload_json JSON NULL COMMENT '步骤输出快照',
          error_message TEXT NULL COMMENT '步骤失败信息',
          retry_count INT NOT NULL DEFAULT 0 COMMENT '当前步骤累计重试次数',
          started_at DATETIME NULL COMMENT '步骤最近一次开始时间',
          finished_at DATETIME NULL COMMENT '步骤最近一次完成时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_step_run_id (step_run_id),
          UNIQUE KEY uk_action_run_step (tenant_id, action_run_id, step_code),
          KEY idx_tenant_action_run (tenant_id, action_run_id, step_order),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审批后动作链步骤明细表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_action_run_step")
    op.execute("DROP TABLE IF EXISTS agent_action_run")
