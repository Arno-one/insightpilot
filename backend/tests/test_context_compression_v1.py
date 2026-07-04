import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


def _cleanup_context_packet_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_customer_context_packet_compresses_memory_under_budget():
    tenant_id = f"tenant_context_packet_{uuid4().hex[:8]}"
    user_id = f"user_context_packet_{uuid4().hex[:8]}"
    customer_id = f"cust_context_packet_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _cleanup_context_packet_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id, industry, region,
                      lifecycle_stage, intent_level, customer_level, competitor_involved,
                      next_follow_up_at, last_follow_up_at, last_sentiment
                    )
                    VALUES (
                      :tenant_id, :customer_id, '上下文压缩测试客户', :user_id, '医疗', '华北',
                      'opportunity', 'high', 'A', 1,
                      :next_follow_up_at, :last_follow_up_at, 'negative'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "next_follow_up_at": now + timedelta(days=1),
                    "last_follow_up_at": now - timedelta(days=2),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_risk_snapshot (
                      tenant_id, risk_snapshot_id, customer_id, owner_user_id, risk_score,
                      risk_level, rule_hits_json, evidence_json, llm_reason, llm_suggestion,
                      suggested_task_json, status, created_at
                    )
                    VALUES (
                      :tenant_id, 'risk_context_packet', :customer_id, :user_id, 91,
                      'high', '[]', '{}', '客户长期未确认预算且竞品介入',
                      '建议主管介入并补充 ROI 证明', '{}', 'pending_review', :created_at
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "created_at": now},
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_context_packet', :customer_id, 'customer',
                      :summary_text, :summary_json, 'run_context_packet', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "summary_text": "客户需要 ROI 证明、竞品对比、主管背书。" * 80,
                    "summary_json": json.dumps(
                        {
                            "profile": {"intent_level": "high", "lifecycle_stage": "opportunity"},
                            "profile_tags": {"risk_tag": "风险:high/91", "competition_tag": "竞品:已介入"},
                        },
                        ensure_ascii=False,
                    ),
                    "last_compiled_at": now,
                },
            )
            db.commit()

            packet = memory_service.build_customer_context_packet(
                db,
                current_user,
                customer_id=customer_id,
                max_chars=700,
            )

        assert packet["source_type"] == "runtime_context_packet"
        assert packet["budget"]["max_chars"] == 700
        assert packet["budget"]["used_chars"] <= 700
        assert packet["budget"]["overflow"] is True
        assert packet["raw_refs"]["customer_memory_id"] == "memory_context_packet"
        assert packet["sections"][0]["section_type"] == "customer_profile"
        assert "上下文压缩测试客户" in packet["compressed_context"]
        assert "当前状态" in packet["compressed_context"]
        assert any(section["section_type"] == "compiled_memory" for section in packet["sections"])
    finally:
        _cleanup_context_packet_fixture(tenant_id, customer_id)
