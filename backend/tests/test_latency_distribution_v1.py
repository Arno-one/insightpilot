from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import router as agent_router
from app.modules.llm.usage import record_llm_call


def _cleanup_latency_fixture(tenant_id: str, run_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM agent_step WHERE tenant_id = :tenant_id AND run_id = :run_id"), {"tenant_id": tenant_id, "run_id": run_id})
        db.execute(text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id = :run_id"), {"tenant_id": tenant_id, "run_id": run_id})
        db.execute(text("DELETE FROM llm_call_log WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def _insert_latency_run(db, tenant_id: str, run_id: str):
    db.execute(
        text(
            """
            INSERT INTO agent_run (
              tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json,
              status, started_at, finished_at, total_duration_ms
            )
            VALUES (
              :tenant_id, :run_id, 'u_latency', 'latency_test', 'latency_graph',
              '{}', '{}', 'success', :started_at, :finished_at, 1500
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "started_at": datetime(2026, 7, 4, 12, 0, 0),
            "finished_at": datetime(2026, 7, 4, 12, 0, 2),
        },
    )


def _insert_latency_step(db, tenant_id: str, run_id: str, step_id: str, duration_ms: int, created_at: datetime):
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, started_at, finished_at, duration_ms, created_at
            )
            VALUES (
              :tenant_id, :step_id, :run_id, 'latency_node', 'latency.tool',
              '{}', '{}', 'success', :started_at, :finished_at, :duration_ms, :created_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_id": step_id,
            "run_id": run_id,
            "duration_ms": duration_ms,
            "started_at": created_at,
            "finished_at": created_at + timedelta(milliseconds=duration_ms),
            "created_at": created_at,
        },
    )


def test_latency_distribution_metrics_include_runtime_llm_and_slow_operations():
    tenant_id = "tenant_latency_distribution_v1"
    run_id = "run_latency_distribution_v1"
    _cleanup_latency_fixture(tenant_id, run_id)

    try:
        with SessionLocal() as db:
            _insert_latency_run(db, tenant_id, run_id)
            base_time = datetime(2026, 7, 4, 12, 10, 0)
            for index, duration_ms in enumerate([100, 200, 400, 800], start=1):
                _insert_latency_step(
                    db,
                    tenant_id,
                    run_id,
                    f"step_latency_{index}",
                    duration_ms,
                    base_time + timedelta(seconds=index),
                )
            db.commit()

        record_llm_call(
            tenant_id=tenant_id,
            source="nl2sql.generate_sql",
            model="deepseek-chat",
            status="success",
            total_tokens=120,
            latency_ms=1000,
        )
        record_llm_call(
            tenant_id=tenant_id,
            source="RiskAdvice",
            model="deepseek-chat",
            status="success",
            total_tokens=80,
            latency_ms=3000,
        )

        with SessionLocal() as db:
            metrics = agent_router._build_latency_distribution_metrics(db, tenant_id, limit=20)

        assert metrics["runtime"]["sample_size"] == 4
        assert metrics["runtime"]["p50_ms"] == 300
        assert metrics["runtime"]["p95_ms"] == 740
        assert metrics["runtime"]["p99_ms"] == 788
        assert metrics["llm"]["sample_size"] == 2
        assert metrics["llm"]["p50_ms"] == 2000
        assert metrics["slow_operations"][0]["operation_type"] == "llm_call"
        assert metrics["slow_operations"][0]["duration_ms"] == 3000
    finally:
        _cleanup_latency_fixture(tenant_id, run_id)
