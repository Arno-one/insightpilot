"""新增客户原子长期记忆表
Revision ID: 20260708_customer_memory_atomic
Revises: 20260704_1016_add_memory_governance_state
Create Date: 2026-07-08 11:00:00
"""

from alembic import op


revision = "20260708_customer_memory_atomic"
down_revision = "20260704_1016_add_memory_governance_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_memory_atomic (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          atomic_memory_id VARCHAR(64) NOT NULL COMMENT '原子记忆业务主键',
          memory_id VARCHAR(64) NOT NULL COMMENT '关联 summary 层 memory_id',
          customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
          memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer' COMMENT '记忆范围，V1 固定为 customer',
          memory_type VARCHAR(30) NOT NULL COMMENT '记忆类型：world / experience / opinion / observation',
          order_index INT NOT NULL DEFAULT 0 COMMENT '单客户全量重建后的稳定顺序',
          title VARCHAR(255) NULL COMMENT '原子记忆标题',
          content TEXT NOT NULL COMMENT '原子记忆正文',
          confidence DECIMAL(6,4) NULL COMMENT '观点类记忆置信度，非观点可为空',
          occurred_at DATETIME NULL COMMENT '该记忆对应事件发生时间',
          source_table VARCHAR(64) NOT NULL COMMENT '来源业务表',
          source_id VARCHAR(64) NULL COMMENT '来源业务主键',
          source_run_id VARCHAR(64) NULL COMMENT '来源 Agent Run ID',
          evidence_refs_json JSON NULL COMMENT '证据引用列表 JSON',
          entity_keys_json JSON NULL COMMENT '实体键列表 JSON',
          metadata_json JSON NULL COMMENT '扩展元数据 JSON',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
          UNIQUE KEY uk_atomic_memory_id (atomic_memory_id),
          KEY idx_tenant_customer_type_time (tenant_id, customer_id, memory_type, occurred_at),
          KEY idx_tenant_memory_order (tenant_id, memory_id, order_index),
          KEY idx_tenant_source_run (tenant_id, source_run_id),
          KEY idx_tenant_source_table (tenant_id, source_table, source_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户长期记忆原子层，存储事实、经验、观点与总结明细'
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customer_memory_atomic")
