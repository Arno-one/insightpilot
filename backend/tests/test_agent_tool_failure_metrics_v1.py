from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import router as agent_router


def _cleanup_tool_metric_steps(tenant_id: str, run_ids: list[str]):
    with SessionLocal() as db:
        for run_id in run_ids:
            db.execute(
                text("DELETE FROM agent_step WHERE tenant_id = :tenant_id AND run_id = :run_id"),
                {"tenant_id": tenant_id, "run_id": run_id},
            )
            db.execute(
                text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id = :run_id"),
                {"tenant_id": tenant_id, "run_id": run_id},
            )
        db.commit()


def _insert_tool_metric_run(db, tenant_id: str, run_id: str, user_id: str):
    db.execute(
        text(
            """
            INSERT INTO agent_run (
              tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json,
              status, started_at, finished_at, total_duration_ms
            )
            VALUES (
              :tenant_id, :run_id, :user_id, 'metric_test', 'metric_test_graph',
              '{}', '{}', 'success', :started_at, :finished_at, 0
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "user_id": user_id,
            "started_at": datetime(2026, 7, 4, 10, 0, 0),
            "finished_at": datetime(2026, 7, 4, 10, 0, 1),
        },
    )


def _insert_tool_metric_step(
    db,
    *,
    tenant_id: str,
    run_id: str,
    step_id: str,
    tool_name: str,
    status: str,
    duration_ms: int,
    created_at: datetime,
    error_message: str | None = None,
):
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, error_message, started_at, finished_at, duration_ms, created_at
            )
            VALUES (
              :tenant_id, :step_id, :run_id, 'metric_node', :tool_name, '{}', '{}',
              :status, :error_message, :started_at, :finished_at, :duration_ms, :created_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_id": step_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "status": status,
            "error_message": error_message,
            "started_at": created_at,
            "finished_at": created_at + timedelta(milliseconds=duration_ms),
            "duration_ms": duration_ms,
            "created_at": created_at,
        },
    )


def test_tool_failure_metrics_aggregate_by_tool_name():
    # 中文注释：使用独立测试租户，避免 demo_tenant 的历史演示 Step 把 limit 样本窗口挤掉。
    tenant_id = "tenant_tool_metrics_v1"
    user_id = "u_metrics"
    run_id = "run_tool_metrics_v1"
    _cleanup_tool_metric_steps(tenant_id, [run_id])

    try:
        with SessionLocal() as db:
            _insert_tool_metric_run(db, tenant_id, run_id, user_id)
            base_time = datetime(2026, 7, 4, 11, 0, 0)
            _insert_tool_metric_step(
                db,
                tenant_id=tenant_id,
                run_id=run_id,
                step_id="step_metric_success",
                tool_name="data.query_sql",
                status="success",
                duration_ms=10,
                created_at=base_time,
            )
            _insert_tool_metric_step(
                db,
                tenant_id=tenant_id,
                run_id=run_id,
                step_id="step_metric_failed",
                tool_name="data.query_sql",
                status="failed",
                duration_ms=30,
                created_at=base_time + timedelta(seconds=1),
                error_message="模拟 SQL 工具失败",
            )
            _insert_tool_metric_step(
                db,
                tenant_id=tenant_id,
                run_id=run_id,
                step_id="step_metric_skipped",
                tool_name="agent_chat_coordinator_v1",
                status="skipped",
                duration_ms=0,
                created_at=base_time + timedelta(seconds=2),
            )
            db.commit()

            metrics = agent_router._build_tool_failure_metrics(db, tenant_id, limit=20)

        sql_tool = next(item for item in metrics["tools"] if item["tool_name"] == "data.query_sql")
        coordinator_tool = next(item for item in metrics["tools"] if item["tool_name"] == "agent_chat_coordinator_v1")

        assert metrics["sample_size"] >= 3
        assert sql_tool["total_count"] == 2
        assert sql_tool["success_count"] == 1
        assert sql_tool["failed_count"] == 1
        assert sql_tool["failure_rate"] == 0.5
        assert sql_tool["avg_duration_ms"] == 20
        assert sql_tool["latest_failed_step"]["step_id"] == "step_metric_failed"
        assert coordinator_tool["skipped_count"] == 1
    finally:
        _cleanup_tool_metric_steps(tenant_id, [run_id])
