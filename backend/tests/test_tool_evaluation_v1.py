from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_tool_eval_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM tool_evaluation_result WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_tool_evaluation_records_success_rate_and_failure_taxonomy():
    tenant_id = "tenant_tool_eval_v1"
    user_id = "u_tool_eval"
    _cleanup_tool_eval_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            dataset = service.create_dataset(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                name="Tool 成功率评测集",
                description="用于统计工具调用成功率和失败原因分类",
                target_type="tool",
            )
            sql_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="SQL 工具可正常查询",
                user_input="查询本月高风险客户数量",
                expected_behavior="工具应返回结构化查询结果",
                target_type="tool",
                target_name="data.query_sql",
                tags=["success-rate"],
            )
            notify_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="通知工具缺少权限时失败分类清晰",
                user_input="发送一封审批提醒邮件",
                expected_behavior="缺少权限时应归类为 permission_denied",
                target_type="tool",
                target_name="notification.send_email",
                tags=["failure-taxonomy"],
            )
            success_result = service.create_tool_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=sql_case["case_id"],
                tool_name="data.query_sql",
                run_id="run_tool_eval_success",
                step_id="step_tool_eval_success",
                status="success",
                expected_status="success",
                elapsed_ms=20,
                metadata_json={"row_count": 1},
            )
            service.create_tool_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=notify_case["case_id"],
                tool_name="notification.send_email",
                run_id="run_tool_eval_failed",
                step_id="step_tool_eval_failed",
                status="failed",
                expected_status="success",
                failure_reason_category="permission_denied",
                failure_reason="缺少 notification:send 权限",
                elapsed_ms=40,
            )
            service.create_tool_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=sql_case["case_id"],
                tool_name="data.query_sql",
                run_id="run_tool_eval_skipped",
                step_id="step_tool_eval_skipped",
                status="skipped",
                expected_status="success",
                failure_reason_category="precondition_missing",
                failure_reason="缺少必需客户上下文",
                elapsed_ms=0,
            )
            summary = service.summarize_tool_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
            )
            sql_summary = service.summarize_tool_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
                tool_name="data.query_sql",
            )

        assert success_result["metadata_json"]["row_count"] == 1
        assert summary["total_count"] == 3
        assert summary["success_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["skipped_count"] == 1
        assert summary["success_rate"] == 0.3333
        assert summary["failure_rate"] == 0.3333
        assert summary["avg_elapsed_ms"] == 20
        assert summary["failure_reason_distribution"][0]["category"] == "permission_denied"
        assert summary["failure_reason_distribution"][0]["count"] == 1
        assert summary["latest_failures"][0]["step_id"] == "step_tool_eval_failed"
        assert sql_summary["total_count"] == 2
        assert sql_summary["by_tool"][0]["tool_name"] == "data.query_sql"
        assert sql_summary["by_tool"][0]["success_rate"] == 0.5
    finally:
        _cleanup_tool_eval_fixture(tenant_id)
