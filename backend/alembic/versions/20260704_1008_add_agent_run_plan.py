"""新增 Agent Run Plan 执行计划表

Revision ID: 20260704_agent_run_plan
Revises: 20260704_nl2sql_persistence
Create Date: 2026-07-04 10:08:00
"""

from alembic import op


revision = "20260704_agent_run_plan"
down_revision = "20260704_nl2sql_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_plan (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          plan_id VARCHAR(64) NOT NULL COMMENT 'Agent Run Plan 业务主键',
          run_id VARCHAR(64) NOT NULL COMMENT '关联 Agent Run ID',
          user_id VARCHAR(64) NOT NULL COMMENT '计划发起用户 ID',
          plan_type VARCHAR(50) NOT NULL DEFAULT 'single_tool' COMMENT '计划类型：single_tool / multi_step / recovery',
          plan_title VARCHAR(120) NOT NULL COMMENT '计划标题',
          objective_summary TEXT NULL COMMENT '计划目标摘要',
          status VARCHAR(30) NOT NULL DEFAULT 'created' COMMENT '计划状态：created / running / success / failed / partial',
          source_intent VARCHAR(50) NULL COMMENT '来源意图快照',
          planned_at DATETIME NOT NULL COMMENT '计划生成时间',
          started_at DATETIME NULL COMMENT '计划开始执行时间',
          finished_at DATETIME NULL COMMENT '计划结束时间',
          metadata_json JSON NULL COMMENT '计划扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_plan_id (plan_id),
          KEY idx_tenant_run (tenant_id, run_id),
          KEY idx_tenant_user_planned (tenant_id, user_id, planned_at),
          KEY idx_tenant_status_planned (tenant_id, status, planned_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent Run 执行计划表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_run_plan_step (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          plan_step_id VARCHAR(64) NOT NULL COMMENT '计划步骤业务主键',
          plan_id VARCHAR(64) NOT NULL COMMENT '所属 Agent Run Plan ID',
          run_id VARCHAR(64) NOT NULL COMMENT '关联 Agent Run ID',
          step_code VARCHAR(80) NOT NULL COMMENT '计划步骤编码',
          step_order INT NOT NULL COMMENT '计划步骤顺序',
          step_title VARCHAR(120) NOT NULL COMMENT '计划步骤标题',
          step_type VARCHAR(50) NOT NULL DEFAULT 'tool_call' COMMENT '步骤类型：tool_call / planner / coordinator / human_gate',
          tool_name VARCHAR(80) NULL COMMENT '计划调用的工具名称',
          depends_on_json JSON NULL COMMENT '依赖步骤编码数组 JSON',
          status VARCHAR(30) NOT NULL DEFAULT 'created' COMMENT '步骤状态：created / running / success / failed / skipped',
          input_summary TEXT NULL COMMENT '步骤输入摘要',
          output_summary TEXT NULL COMMENT '步骤输出摘要',
          linked_step_id VARCHAR(64) NULL COMMENT '关联真实 Agent Step ID',
          error_message TEXT NULL COMMENT '错误信息',
          metadata_json JSON NULL COMMENT '步骤扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_plan_step_id (plan_step_id),
          KEY idx_tenant_plan_order (tenant_id, plan_id, step_order),
          KEY idx_tenant_run (tenant_id, run_id),
          KEY idx_tenant_status (tenant_id, status),
          KEY idx_linked_step_id (linked_step_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent Run 执行计划步骤表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_run_plan_step")
    op.execute("DROP TABLE IF EXISTS agent_run_plan")
