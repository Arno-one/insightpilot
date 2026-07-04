from types import SimpleNamespace

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import router as agent_router
from app.modules.llm.usage import extract_token_usage, record_llm_call


def _cleanup_llm_usage_logs(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM llm_call_log WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_extract_token_usage_supports_openai_response_object():
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=45,
            total_tokens=165,
        )
    )

    usage = extract_token_usage(response)

    assert usage == {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
    }


def test_llm_usage_metrics_aggregate_by_source_and_model():
    tenant_id = "tenant_llm_usage_v1"
    _cleanup_llm_usage_logs(tenant_id)

    try:
        record_llm_call(
            tenant_id=tenant_id,
            user_id="u_llm_metrics",
            source="nl2sql.generate_sql",
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
            latency_ms=800,
            estimated_cost="0.000000",
            metadata_json={"query_id": "query_llm_usage_v1"},
        )
        record_llm_call(
            tenant_id=tenant_id,
            user_id="u_llm_metrics",
            source="RiskAdvice",
            model="deepseek-chat",
            status="failed",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=1200,
            error_message="模拟 LLM 调用失败",
        )

        with SessionLocal() as db:
            metrics = agent_router._build_llm_usage_metrics(db, tenant_id, limit=20)

        nl2sql_group = next(item for item in metrics["groups"] if item["source"] == "nl2sql.generate_sql")

        assert metrics["sample_size"] == 2
        assert metrics["call_count"] == 2
        assert metrics["failed_count"] == 1
        assert metrics["total_tokens"] == 140
        assert metrics["avg_latency_ms"] == 1000
        assert metrics["latest_failed_call"]["source"] == "RiskAdvice"
        assert nl2sql_group["model"] == "deepseek-chat"
        assert nl2sql_group["call_count"] == 1
        assert nl2sql_group["total_tokens"] == 140
    finally:
        _cleanup_llm_usage_logs(tenant_id)
