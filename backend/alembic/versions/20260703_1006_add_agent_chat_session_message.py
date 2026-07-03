"""新增统一 Agent 对话会话与消息表

Revision ID: 20260703_agent_chat_session
Revises: 20260703_action_chain_runtime
Create Date: 2026-07-04 00:20:00
"""

from alembic import op


revision = "20260703_agent_chat_session"
down_revision = "20260703_action_chain_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_chat_session (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          session_id VARCHAR(64) NOT NULL COMMENT '统一 Agent 对话会话业务主键',
          user_id VARCHAR(64) NOT NULL COMMENT '会话发起用户 ID',
          agent_scope VARCHAR(50) NOT NULL DEFAULT 'general' COMMENT '会话所属 Agent 范围，如 general / risk / data',
          intent VARCHAR(50) NOT NULL DEFAULT 'unknown' COMMENT '当前会话主意图，如 risk_analysis / customer_query / report_query / data_query',
          title VARCHAR(120) NOT NULL DEFAULT '新对话' COMMENT '会话标题',
          status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '会话状态：active / closed / archived',
          related_customer_id VARCHAR(64) NULL COMMENT '关联客户 ID，客户类对话使用',
          memory_key VARCHAR(180) NULL COMMENT '短期记忆键，兼容现有 Redis Risk Chat 记忆',
          context_json JSON NULL COMMENT '会话上下文快照 JSON',
          last_message_role VARCHAR(30) NULL COMMENT '最后一条消息角色',
          last_message_preview VARCHAR(255) NULL COMMENT '最后一条消息预览',
          message_count INT NOT NULL DEFAULT 0 COMMENT '会话消息总数',
          last_message_at DATETIME NULL COMMENT '最后一条消息时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_session_id (session_id),
          KEY idx_tenant_user_updated (tenant_id, user_id, updated_at),
          KEY idx_tenant_scope_intent (tenant_id, agent_scope, intent),
          KEY idx_tenant_customer_updated (tenant_id, related_customer_id, updated_at),
          KEY idx_tenant_status_updated (tenant_id, status, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一 Agent 对话会话表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_chat_message (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          message_id VARCHAR(64) NOT NULL COMMENT '统一 Agent 对话消息业务主键',
          session_id VARCHAR(64) NOT NULL COMMENT '所属统一 Agent 对话会话 ID',
          user_id VARCHAR(64) NOT NULL COMMENT '消息所属用户 ID',
          role VARCHAR(30) NOT NULL COMMENT '消息角色：user / assistant / system / tool',
          content TEXT NOT NULL COMMENT '消息正文',
          intent VARCHAR(50) NULL COMMENT '消息级意图快照',
          tool_name VARCHAR(120) NULL COMMENT '工具消息对应的工具名',
          run_id VARCHAR(64) NULL COMMENT '关联 Agent Run ID',
          trace_id VARCHAR(64) NULL COMMENT '关联 Trace ID',
          metadata_json JSON NULL COMMENT '消息扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_message_id (message_id),
          KEY idx_tenant_session_created (tenant_id, session_id, created_at),
          KEY idx_tenant_user_created (tenant_id, user_id, created_at),
          KEY idx_tenant_run (tenant_id, run_id),
          KEY idx_tenant_trace (tenant_id, trace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='统一 Agent 对话消息表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_chat_message")
    op.execute("DROP TABLE IF EXISTS agent_chat_session")
