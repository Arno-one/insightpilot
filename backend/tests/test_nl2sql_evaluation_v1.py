from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_nl2sql_eval_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM nl2sql_evaluation_result WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_nl2sql_evaluation_records_results_and_summary():
    tenant_id = "tenant_nl2sql_eval_v1"
    user_id = "u_nl2sql_eval"
    _cleanup_nl2sql_eval_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            dataset = service.create_dataset(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                name="NL2SQL 执行成功率集",
                description="用于统计 SQL 执行成功率",
                target_type="nl2sql",
            )
            success_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="统计高风险客户",
                user_input="本月高风险客户有多少个？",
                expected_behavior="返回一个数量字段。",
                target_type="nl2sql",
                target_name="nl2sql.generate_sql",
            )
            failed_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="非法字段测试",
                user_input="查询不存在字段。",
                expected_behavior="应返回校验失败原因。",
                target_type="nl2sql",
                target_name="nl2sql.generate_sql",
            )
            success_result = service.create_nl2sql_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=success_case["case_id"],
                query_id="query_eval_success",
                generated_sql="SELECT COUNT(*) AS total FROM crm_customer WHERE tenant_id = :tenant_id",
                status="executed",
                row_count=1,
                elapsed_ms=120,
                metadata_json={"validator": {"valid": True}},
            )
            service.create_nl2sql_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=failed_case["case_id"],
                query_id="query_eval_failed",
                generated_sql="SELECT missing_field FROM crm_customer",
                status="failed",
                row_count=0,
                error_message="字段不存在",
                elapsed_ms=80,
            )
            summary = service.summarize_nl2sql_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
            )

        assert success_result["row_count"] == 1
        assert success_result["metadata_json"]["validator"]["valid"] is True
        assert summary["total_count"] == 2
        assert summary["success_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["success_rate"] == 0.5
        assert summary["total_row_count"] == 1
        assert summary["avg_elapsed_ms"] == 100
        assert summary["latest_errors"][0]["error_message"] == "字段不存在"
    finally:
        _cleanup_nl2sql_eval_fixture(tenant_id)
