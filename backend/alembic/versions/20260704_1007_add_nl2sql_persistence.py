"""新增 NL2SQL 会话、消息与审计表

Revision ID: 20260704_nl2sql_persistence
Revises: 20260703_agent_chat_session
Create Date: 2026-07-04 10:07:00
"""

from alembic import op


revision = "20260704_nl2sql_persistence"
down_revision = "20260703_agent_chat_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nl2sql_session (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          session_id VARCHAR(64) NOT NULL COMMENT 'NL2SQL 会话业务主键',
          user_id VARCHAR(64) NOT NULL COMMENT '发起用户 ID',
          title VARCHAR(120) NOT NULL DEFAULT '数据问答会话' COMMENT '会话标题',
          status VARCHAR(30) NOT NULL DEFAULT 'active' COMMENT '会话状态：active / closed / archived',
          data_scope VARCHAR(30) NOT NULL DEFAULT 'self' COMMENT '本会话数据范围：self / team / all',
          context_json JSON NULL COMMENT '会话上下文快照 JSON',
          last_question TEXT NULL COMMENT '最后一次用户问题',
          last_query_status VARCHAR(30) NULL COMMENT '最后一次查询状态',
          message_count INT NOT NULL DEFAULT 0 COMMENT '会话消息数量',
          last_message_at DATETIME NULL COMMENT '最后一条消息时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_session_id (session_id),
          KEY idx_tenant_user_updated (tenant_id, user_id, updated_at),
          KEY idx_tenant_status_updated (tenant_id, status, updated_at),
          KEY idx_tenant_scope_updated (tenant_id, data_scope, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NL2SQL 数据问答会话表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nl2sql_message (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          message_id VARCHAR(64) NOT NULL COMMENT 'NL2SQL 消息业务主键',
          session_id VARCHAR(64) NOT NULL COMMENT '所属 NL2SQL 会话 ID',
          user_id VARCHAR(64) NOT NULL COMMENT '消息所属用户 ID',
          role VARCHAR(30) NOT NULL COMMENT '消息角色：user / assistant / system / tool',
          content TEXT NOT NULL COMMENT '消息正文',
          query_id VARCHAR(64) NULL COMMENT '关联查询审计 ID',
          question TEXT NULL COMMENT '用户自然语言问题，兼容独立 NL2SQL 历史展示',
          generated_sql TEXT NULL COMMENT '本轮生成 SQL 快照',
          result_json JSON NULL COMMENT '查询结果 JSON 快照',
          cost_ms INT NOT NULL DEFAULT 0 COMMENT 'LLM 或缓存阶段耗时毫秒',
          is_cached TINYINT NOT NULL DEFAULT 0 COMMENT '是否命中缓存：0 否，1 是',
          metadata_json JSON NULL COMMENT '消息扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_message_id (message_id),
          KEY idx_tenant_session_created (tenant_id, session_id, created_at),
          KEY idx_tenant_user_created (tenant_id, user_id, created_at),
          KEY idx_tenant_query (tenant_id, query_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NL2SQL 数据问答消息表'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nl2sql_query_audit (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          query_id VARCHAR(64) NOT NULL COMMENT 'NL2SQL 查询审计业务主键',
          session_id VARCHAR(64) NOT NULL COMMENT '所属 NL2SQL 会话 ID',
          user_id VARCHAR(64) NOT NULL COMMENT '发起用户 ID',
          question TEXT NOT NULL COMMENT '原始自然语言问题',
          generated_sql TEXT NULL COMMENT '生成的 SQL，V1 后续阶段写入',
          normalized_sql TEXT NULL COMMENT '格式化后的 SQL，V1 后续阶段写入',
          status VARCHAR(30) NOT NULL DEFAULT 'created' COMMENT '查询状态：created / validated / executed / failed',
          validator_result_json JSON NULL COMMENT 'SQL 校验结果 JSON',
          execution_summary_json JSON NULL COMMENT '执行摘要 JSON',
          row_count INT NULL COMMENT '返回行数',
          error_message TEXT NULL COMMENT '错误信息',
          elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '总耗时毫秒',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          finished_at DATETIME NULL COMMENT '结束时间',
          UNIQUE KEY uk_query_id (query_id),
          KEY idx_tenant_session_created (tenant_id, session_id, created_at),
          KEY idx_tenant_user_created (tenant_id, user_id, created_at),
          KEY idx_tenant_status_created (tenant_id, status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='NL2SQL 查询审计表'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl2sql_query_audit")
    op.execute("DROP TABLE IF EXISTS nl2sql_message")
    op.execute("DROP TABLE IF EXISTS nl2sql_session")
