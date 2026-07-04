from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_agent_eval_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM agent_evaluation_result WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_agent_evaluation_records_completion_rate_and_failure_reasons():
    tenant_id = "tenant_agent_eval_v1"
    user_id = "u_agent_eval"
    _cleanup_agent_eval_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            dataset = service.create_dataset(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                name="Agent 完成率评测集",
                description="用于统计 Agent 任务完成率和失败归因",
                target_type="agent",
            )
            decision_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="经营决策 Agent 完成建议生成",
                user_input="哪些客户需要优先跟进？",
                expected_behavior="返回可执行的优先级和原因",
                target_type="agent",
                target_name="manager_decision",
                tags=["completion"],
            )
            action_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="执行 Agent 缺少审批上下文时失败",
                user_input="帮我直接发通知给销售",
                expected_behavior="缺少审批时应失败并输出原因",
                target_type="agent",
                target_name="action_execution",
                tags=["failure"],
            )
            completed = service.create_agent_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=decision_case["case_id"],
                agent_type="manager_decision",
                agent_name="经营决策 Agent",
                run_id="run_agent_eval_completed",
                status="completed",
                completion_score=1,
                elapsed_ms=300,
                metadata_json={"answer_sections": 3},
            )
            service.create_agent_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=action_case["case_id"],
                agent_type="action_execution",
                agent_name="执行 Agent",
                run_id="run_agent_eval_failed",
                status="failed",
                completion_score=0,
                failure_reason_category="approval_required",
                failure_reason="外发通知前缺少审批任务",
                elapsed_ms=120,
            )
            service.create_agent_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=decision_case["case_id"],
                agent_type="manager_decision",
                agent_name="经营决策 Agent",
                run_id="run_agent_eval_partial",
                status="partial",
                completion_score=0.5,
                failure_reason_category="insufficient_context",
                failure_reason="缺少客户近期互动上下文",
                elapsed_ms=180,
            )
            summary = service.summarize_agent_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
            )
            decision_summary = service.summarize_agent_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
                agent_type="manager_decision",
            )

        assert completed["completion_score"] == 1
        assert completed["metadata_json"]["answer_sections"] == 3
        assert summary["total_count"] == 3
        assert summary["completed_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["partial_count"] == 1
        assert summary["completion_rate"] == 0.3333
        assert summary["failure_rate"] == 0.3333
        assert summary["avg_completion_score"] == 0.5
        assert summary["avg_elapsed_ms"] == 200
        assert summary["failure_reason_distribution"][0]["count"] == 1
        assert summary["latest_failures"][0]["run_id"] in {"run_agent_eval_failed", "run_agent_eval_partial"}
        assert decision_summary["total_count"] == 2
        assert decision_summary["by_agent"][0]["agent_type"] == "manager_decision"
        assert decision_summary["by_agent"][0]["completion_rate"] == 0.5
    finally:
        _cleanup_agent_eval_fixture(tenant_id)
