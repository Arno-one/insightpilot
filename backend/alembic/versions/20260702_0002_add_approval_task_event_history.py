"""新增审批与任务操作留痕表

Revision ID: 20260702_0002
Revises: 20260701_0001
Create Date: 2026-07-02 16:30:00
"""

from alembic import op


revision = "20260702_0002"
down_revision = "20260701_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_task_event (
          id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '数据库自增主键',
          tenant_id VARCHAR(64) NOT NULL COMMENT '所属租户 ID',
          event_id VARCHAR(64) NOT NULL COMMENT '事件业务主键',
          entity_type VARCHAR(20) NOT NULL COMMENT '事件主体类型：approval / task',
          entity_id VARCHAR(64) NOT NULL COMMENT '事件主体业务 ID',
          approval_id VARCHAR(64) NULL COMMENT '关联审批 ID',
          task_id VARCHAR(64) NULL COMMENT '关联任务 ID',
          customer_id VARCHAR(64) NOT NULL COMMENT '所属客户 ID',
          risk_snapshot_id VARCHAR(64) NULL COMMENT '关联风险快照 ID',
          action_type VARCHAR(50) NOT NULL COMMENT '动作类型，例如 approval_created / task_completed',
          operator_user_id VARCHAR(64) NOT NULL COMMENT '操作人用户 ID',
          note TEXT NULL COMMENT '动作说明或备注',
          detail_json JSON NULL COMMENT '动作补充细节 JSON',
          happened_at DATETIME NOT NULL COMMENT '动作发生时间',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
          UNIQUE KEY uk_event_id (event_id),
          KEY idx_tenant_customer_time (tenant_id, customer_id, happened_at),
          KEY idx_tenant_approval_time (tenant_id, approval_id, happened_at),
          KEY idx_tenant_task_time (tenant_id, task_id, happened_at),
          KEY idx_tenant_entity_time (tenant_id, entity_type, entity_id, happened_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='审批与任务关键动作留痕表'
        """
    )

    # 中文注释：把现有审批记录回填成“创建 + 审批结果”事件，避免升级后老数据时间线为空。
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT ar.tenant_id,
               CONCAT('evt_appr_created_', ar.approval_id),
               'approval',
               ar.approval_id,
               ar.approval_id,
               NULL,
               ar.customer_id,
               ar.risk_snapshot_id,
               'approval_created',
               ar.requested_by_user_id,
               'AI 风险建议已进入人工审批队列',
               JSON_OBJECT('approval_type', ar.approval_type, 'status', ar.status),
               ar.created_at
        FROM approval_record ar
        LEFT JOIN approval_task_event e
          ON e.tenant_id = ar.tenant_id
         AND e.event_id = CONCAT('evt_appr_created_', ar.approval_id)
        WHERE e.event_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT ar.tenant_id,
               CONCAT('evt_appr_reviewed_', ar.approval_id),
               'approval',
               ar.approval_id,
               ar.approval_id,
               NULL,
               ar.customer_id,
               ar.risk_snapshot_id,
               CASE WHEN ar.status = 'approved' THEN 'approval_approved' ELSE 'approval_rejected' END,
               ar.reviewer_user_id,
               COALESCE(ar.review_comment, CASE WHEN ar.status = 'approved' THEN '审批通过' ELSE '审批驳回' END),
               JSON_OBJECT('review_comment', ar.review_comment, 'status', ar.status),
               ar.reviewed_at
        FROM approval_record ar
        LEFT JOIN approval_task_event e
          ON e.tenant_id = ar.tenant_id
         AND e.event_id = CONCAT('evt_appr_reviewed_', ar.approval_id)
        WHERE ar.status IN ('approved', 'rejected')
          AND ar.reviewer_user_id IS NOT NULL
          AND ar.reviewed_at IS NOT NULL
          AND e.event_id IS NULL
        """
    )

    # 中文注释：任务侧至少回填创建、开始执行、完成、取消，保证旧任务同样具备可回看轨迹。
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT t.tenant_id,
               CONCAT('evt_task_created_', t.task_id),
               'task',
               t.task_id,
               t.approval_id,
               t.task_id,
               t.customer_id,
               a.risk_snapshot_id,
               'task_created',
               t.creator_user_id,
               '任务已创建，等待执行',
               JSON_OBJECT('title', t.title, 'priority', t.priority, 'status', t.status),
               t.created_at
        FROM sales_task t
        LEFT JOIN approval_record a
          ON a.tenant_id = t.tenant_id
         AND a.approval_id = t.approval_id
        LEFT JOIN approval_task_event e
          ON e.tenant_id = t.tenant_id
         AND e.event_id = CONCAT('evt_task_created_', t.task_id)
        WHERE e.event_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT t.tenant_id,
               CONCAT('evt_task_in_progress_', t.task_id),
               'task',
               t.task_id,
               t.approval_id,
               t.task_id,
               t.customer_id,
               a.risk_snapshot_id,
               'task_in_progress',
               t.assignee_user_id,
               '任务已开始执行',
               JSON_OBJECT('status', t.status, 'result_note', t.result_note),
               t.updated_at
        FROM sales_task t
        LEFT JOIN approval_record a
          ON a.tenant_id = t.tenant_id
         AND a.approval_id = t.approval_id
        LEFT JOIN approval_task_event e
          ON e.tenant_id = t.tenant_id
         AND e.event_id = CONCAT('evt_task_in_progress_', t.task_id)
        WHERE t.status = 'in_progress'
          AND e.event_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT t.tenant_id,
               CONCAT('evt_task_completed_', t.task_id),
               'task',
               t.task_id,
               t.approval_id,
               t.task_id,
               t.customer_id,
               a.risk_snapshot_id,
               'task_completed',
               t.assignee_user_id,
               COALESCE(t.result_note, '任务已完成'),
               JSON_OBJECT('status', t.status, 'result_note', t.result_note),
               t.completed_at
        FROM sales_task t
        LEFT JOIN approval_record a
          ON a.tenant_id = t.tenant_id
         AND a.approval_id = t.approval_id
        LEFT JOIN approval_task_event e
          ON e.tenant_id = t.tenant_id
         AND e.event_id = CONCAT('evt_task_completed_', t.task_id)
        WHERE t.status = 'completed'
          AND t.completed_at IS NOT NULL
          AND e.event_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO approval_task_event (
          tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
          risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
        )
        SELECT t.tenant_id,
               CONCAT('evt_task_cancelled_', t.task_id),
               'task',
               t.task_id,
               t.approval_id,
               t.task_id,
               t.customer_id,
               a.risk_snapshot_id,
               'task_cancelled',
               t.assignee_user_id,
               COALESCE(t.result_note, '任务已取消'),
               JSON_OBJECT('status', t.status, 'result_note', t.result_note),
               t.updated_at
        FROM sales_task t
        LEFT JOIN approval_record a
          ON a.tenant_id = t.tenant_id
         AND a.approval_id = t.approval_id
        LEFT JOIN approval_task_event e
          ON e.tenant_id = t.tenant_id
         AND e.event_id = CONCAT('evt_task_cancelled_', t.task_id)
        WHERE t.status = 'cancelled'
          AND e.event_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS approval_task_event")
