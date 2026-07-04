import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


def _cleanup_customer_working_memory_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM sales_task WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM approval_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM crm_follow_up_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM crm_deal WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.execute(text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"), {"tenant_id": tenant_id, "customer_id": customer_id})
        db.commit()


def test_customer_working_memory_rolls_up_current_customer_state():
    tenant_id = f"tenant_working_memory_{uuid4().hex[:8]}"
    user_id = f"user_working_memory_{uuid4().hex[:8]}"
    customer_id = f"cust_working_memory_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _cleanup_customer_working_memory_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id, industry, region, source,
                      lifecycle_stage, intent_level, customer_level, company_size, decision_maker_status,
                      competitor_involved, next_follow_up_at, last_follow_up_at, last_sentiment
                    )
                    VALUES (
                      :tenant_id, :customer_id, 'Working Memory 测试客户', :user_id, '制造业', '华东', 'import',
                      'opportunity', 'high', 'A', '200-500人', 'identified',
                      1, :next_follow_up_at, :last_follow_up_at, 'negative'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "next_follow_up_at": now + timedelta(days=2),
                    "last_follow_up_at": now - timedelta(days=1),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO crm_deal (
                      tenant_id, deal_id, customer_id, owner_user_id, deal_name, stage,
                      amount, quote_amount, quoted_at, expected_close_at, close_result
                    )
                    VALUES (
                      :tenant_id, 'deal_working_memory', :customer_id, :user_id, '年度采购商机', 'proposal',
                      120000, 98000, :quoted_at, :expected_close_at, 'open'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "quoted_at": now - timedelta(days=3),
                    "expected_close_at": now.date(),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO crm_follow_up_record (
                      tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type,
                      content, sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at
                    )
                    VALUES (
                      :tenant_id, 'follow_working_memory', :customer_id, 'deal_working_memory', :user_id, 'wechat',
                      '客户反馈竞品正在压价', 'negative', '需要重新确认预算', '安排主管复访', :next_follow_up_at, :occurred_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "next_follow_up_at": now + timedelta(days=1),
                    "occurred_at": now - timedelta(hours=3),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_risk_snapshot (
                      tenant_id, risk_snapshot_id, customer_id, deal_id, owner_user_id, risk_score,
                      risk_level, rule_hits_json, evidence_json, llm_reason, llm_suggestion,
                      suggested_task_json, status
                    )
                    VALUES (
                      :tenant_id, 'risk_working_memory', :customer_id, 'deal_working_memory', :user_id, 88,
                      'high', '[]', '{}', '竞品压价且跟进断档', '建议主管介入并确认真实采购时间',
                      '{}', 'pending_review'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id},
            )
            db.execute(
                text(
                    """
                    INSERT INTO approval_record (
                      tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
                      proposed_payload_json, status, requested_by_user_id
                    )
                    VALUES (
                      :tenant_id, 'approval_working_memory', 'agent_task_draft', 'run_working_memory',
                      'risk_working_memory', :customer_id, '{}', 'pending', :user_id
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id},
            )
            db.execute(
                text(
                    """
                    INSERT INTO sales_task (
                      tenant_id, task_id, approval_id, customer_id, deal_id, assignee_user_id, creator_user_id,
                      task_type, title, description, priority, status, due_at
                    )
                    VALUES (
                      :tenant_id, 'task_working_memory', 'approval_working_memory', :customer_id, 'deal_working_memory',
                      :user_id, :user_id, 'follow_up', '主管复访客户', '确认采购节奏与竞品压价情况',
                      'high', 'pending', :due_at
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "due_at": now + timedelta(days=1)},
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_working_memory', :customer_id, 'customer',
                      '客户近期存在高风险，需要主管介入。',
                      :summary_json, 'run_working_memory', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "summary_json": json.dumps({"profile_tags": {"risk_tag": "风险:high/88"}}, ensure_ascii=False),
                    "last_compiled_at": now,
                },
            )
            db.commit()

            working = memory_service.load_customer_working_memory(db, current_user, customer_id=customer_id)

        assert working["source_type"] == "customer_working_memory"
        assert working["profile"]["customer_name"] == "Working Memory 测试客户"
        assert working["profile"]["competitor_involved"] is True
        assert working["risk_state"]["latest_risk_level"] == "high"
        assert working["risk_state"]["latest_risk_score"] == 88
        assert working["opportunity_state"]["open_count"] == 1
        assert working["opportunity_state"]["latest_stage"] == "proposal"
        assert working["follow_up_state"]["latest_sentiment"] == "negative"
        assert working["approval_state"]["pending_count"] == 1
        assert working["task_state"]["active_count"] == 1
        assert working["memory_state"]["memory_id"] == "memory_working_memory"
        assert "优先处理当前风险" in working["recommended_focus"][0]
        assert working["raw_refs"]["deal_count"] == 1
    finally:
        _cleanup_customer_working_memory_fixture(tenant_id, customer_id)
