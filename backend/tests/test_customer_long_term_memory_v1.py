import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


def _ensure_customer_memory_atomic_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS customer_memory_atomic (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  atomic_memory_id VARCHAR(64) NOT NULL,
                  memory_id VARCHAR(64) NOT NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer',
                  memory_type VARCHAR(30) NOT NULL,
                  order_index INT NOT NULL DEFAULT 0,
                  title VARCHAR(255) NULL,
                  content TEXT NOT NULL,
                  confidence DECIMAL(6,4) NULL,
                  occurred_at DATETIME NULL,
                  source_table VARCHAR(64) NOT NULL,
                  source_id VARCHAR(64) NULL,
                  source_run_id VARCHAR(64) NULL,
                  evidence_refs_json JSON NULL,
                  entity_keys_json JSON NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_atomic_memory_id (atomic_memory_id),
                  KEY idx_tenant_customer_type_time (tenant_id, customer_id, memory_type, occurred_at),
                  KEY idx_tenant_memory_order (tenant_id, memory_id, order_index),
                  KEY idx_tenant_source_run (tenant_id, source_run_id),
                  KEY idx_tenant_source_table (tenant_id, source_table, source_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_customer_long_term_memory_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM customer_memory_atomic WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM sales_task WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM approval_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM business_report WHERE tenant_id = :tenant_id AND CAST(risk_top_json AS CHAR) LIKE :pattern"),
            {"tenant_id": tenant_id, "pattern": f"%{customer_id}%"},
        )
        db.execute(
            text("DELETE FROM crm_follow_up_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_deal WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_customer_long_term_memory_rolls_up_preferences_and_history():
    tenant_id = f"tenant_long_memory_{uuid4().hex[:8]}"
    user_id = f"user_long_memory_{uuid4().hex[:8]}"
    customer_id = f"cust_long_memory_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_customer_long_term_memory_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id, industry, region, source,
                      lifecycle_stage, intent_level, customer_level, company_size, budget_min, budget_max,
                      expected_purchase_at, decision_maker_status, competitor_involved, next_follow_up_at,
                      last_follow_up_at, last_sentiment, remark
                    )
                    VALUES (
                      :tenant_id, :customer_id, '长期记忆测试客户', :user_id, '零售', '华南', 'expo',
                      'opportunity', 'high', 'A', '500-1000人', 80000, 150000,
                      :expected_purchase_at, 'identified', 1, :next_follow_up_at,
                      :last_follow_up_at, 'neutral', '偏好 ROI 数据和竞品对比'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "expected_purchase_at": date.today() + timedelta(days=30),
                    "next_follow_up_at": now + timedelta(days=2),
                    "last_follow_up_at": now - timedelta(days=3),
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
                      :tenant_id, 'deal_long_memory', :customer_id, :user_id, '长期记忆商机', 'quotation',
                      160000, 145000, :quoted_at, :expected_close_at, 'open'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "quoted_at": now - timedelta(days=6),
                    "expected_close_at": now.date() + timedelta(days=21),
                },
            )
            for index, occurred_days in enumerate([12, 7, 2], start=1):
                db.execute(
                    text(
                        """
                        INSERT INTO crm_follow_up_record (
                          tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type,
                          content, sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at
                        )
                        VALUES (
                          :tenant_id, :follow_up_id, :customer_id, 'deal_long_memory', :user_id, :follow_up_type,
                          :content, :sentiment, :customer_feedback, :next_action, :next_follow_up_at, :occurred_at
                        )
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "follow_up_id": f"follow_long_memory_{index}",
                        "customer_id": customer_id,
                        "user_id": user_id,
                        "follow_up_type": "wechat" if index < 3 else "phone",
                        "content": "客户持续要求补充 ROI 和竞品对比材料",
                        "sentiment": "positive" if index == 3 else "neutral",
                        "customer_feedback": f"第 {index} 次反馈：需要更清楚的投入产出说明",
                        "next_action": "补充 ROI 测算并约下次复盘",
                        "next_follow_up_at": now + timedelta(days=index),
                        "occurred_at": now - timedelta(days=occurred_days),
                    },
                )
            db.execute(
                text(
                    """
                    INSERT INTO customer_risk_snapshot (
                      tenant_id, risk_snapshot_id, customer_id, deal_id, owner_user_id, risk_score,
                      risk_level, rule_hits_json, evidence_json, llm_reason, llm_suggestion,
                      suggested_task_json, status, created_at
                    )
                    VALUES (
                      :tenant_id, 'risk_long_memory', :customer_id, 'deal_long_memory', :user_id, 72,
                      'medium', '[]', '{}', '客户仍在比较竞品 ROI', '建议提供量化收益证明',
                      '{}', 'pending_review', :created_at
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "created_at": now},
            )
            db.execute(
                text(
                    """
                    INSERT INTO approval_record (
                      tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
                      proposed_payload_json, status, requested_by_user_id, created_at
                    )
                    VALUES (
                      :tenant_id, 'approval_long_memory', 'agent_task_draft', 'run_long_memory',
                      'risk_long_memory', :customer_id, '{}', 'approved', :user_id, :created_at
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "created_at": now},
            )
            db.execute(
                text(
                    """
                    INSERT INTO sales_task (
                      tenant_id, task_id, approval_id, customer_id, deal_id, assignee_user_id, creator_user_id,
                      task_type, title, description, priority, status, completed_at, result_note
                    )
                    VALUES (
                      :tenant_id, 'task_long_memory', 'approval_long_memory', :customer_id, 'deal_long_memory',
                      :user_id, :user_id, 'follow_up', '发送 ROI 材料', '补充客户关注的 ROI 说明',
                      'medium', 'completed', :completed_at, '客户认可 ROI 说明，但要求继续补充竞品对照'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "completed_at": now},
            )
            db.execute(
                text(
                    """
                    INSERT INTO business_report (
                      tenant_id, report_id, run_id, report_type, report_date, summary, metrics_json,
                      risk_top_json, suggestions, created_by_user_id
                    )
                    VALUES (
                      :tenant_id, 'report_long_memory', NULL, 'daily', :report_date, '客户长期关注 ROI 和竞品对比。',
                      '{}', :risk_top_json, '准备更清晰的收益测算材料。', :user_id
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "report_date": date.today(),
                    "risk_top_json": json.dumps([{"customer_id": customer_id}], ensure_ascii=False),
                    "user_id": user_id,
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_long_memory', :customer_id, 'customer',
                      '客户长期关注 ROI、竞品对比和投入产出证明。',
                      :summary_json, 'run_long_memory', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "summary_json": json.dumps(
                        {
                            "profile": {"intent_level": "high", "lifecycle_stage": "opportunity"},
                            "profile_tags": {
                                "intent_tag": "意向:high",
                                "competition_tag": "竞品:已介入",
                                "engagement_tag": "互动:活跃",
                            },
                        },
                        ensure_ascii=False,
                    ),
                    "last_compiled_at": now,
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory_atomic (
                      tenant_id, atomic_memory_id, memory_id, customer_id, memory_scope, memory_type,
                      order_index, title, content, confidence, occurred_at, source_table, source_id,
                      source_run_id, evidence_refs_json, entity_keys_json, metadata_json
                    )
                    VALUES
                      (:tenant_id, 'atom_long_world', 'memory_long_memory', :customer_id, 'customer', 'world',
                       1, '客户画像事实', '客户长期关注 ROI、竞品对比和投入产出证明。', NULL, :occurred_at, 'crm_customer', :customer_id,
                       'run_long_memory', '[]', '[]', '{}'),
                      (:tenant_id, 'atom_long_opinion', 'memory_long_memory', :customer_id, 'customer', 'opinion',
                       2, '风险判断', '系统判断客户仍在比较竞品 ROI，需要量化收益证明。', 0.8200, :occurred_at, 'customer_risk_snapshot', 'risk_long_memory',
                       'run_long_memory', '[]', '[]', '{}'),
                      (:tenant_id, 'atom_long_observation', 'memory_long_memory', :customer_id, 'customer', 'observation',
                       3, '客户长期总结', '客户长期关注 ROI、竞品对比和投入产出证明。', NULL, :occurred_at, 'customer_memory', :customer_id,
                       'run_long_memory', '[]', '[]', '{}')
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "occurred_at": now,
                },
            )
            db.commit()

            long_term = memory_service.load_customer_long_term_memory(db, current_user, customer_id=customer_id)

        assert long_term["source_type"] == "customer_long_term_memory"
        assert long_term["long_term_profile"]["customer_name"] == "长期记忆测试客户"
        assert long_term["long_term_profile"]["competitor_involved"] is True
        assert "竞品:已介入" in long_term["long_term_profile"]["stable_traits"]
        assert long_term["preference_state"]["industry"] == "零售"
        assert long_term["preference_state"]["budget_range"] == {"min": 80000, "max": 150000}
        assert long_term["preference_state"]["preferred_follow_up_type"] == "wechat"
        assert len(long_term["preference_state"]["feedback_samples"]) == 3
        assert long_term["behavior_state"]["follow_up_count"] == 3
        assert long_term["behavior_state"]["risk_level_history"][0]["risk_level"] == "medium"
        assert long_term["behavior_state"]["task_result_history"][0]["status"] == "completed"
        assert long_term["memory_state"]["memory_id"] == "memory_long_memory"
        assert long_term["memory_state"]["atomic_memory_count"] == 3
        assert long_term["memory_quality"]["has_compiled_memory"] is True
        assert long_term["memory_quality"]["has_atomic_memory"] is True
        assert long_term["recall_summary"]["by_type"]["opinion"] == 1
        assert len(long_term["memory_groups"]["world"]) == 1
        assert long_term["memory_groups"]["opinion"][0]["confidence"] == 0.82
        assert "wechat" in long_term["recommended_usage"][0]
    finally:
        _cleanup_customer_long_term_memory_fixture(tenant_id, customer_id)
