from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_evaluation_overview_fixture(tenant_id: str):
    with SessionLocal() as db:
        for table_name in [
            "agent_evaluation_result",
            "tool_evaluation_result",
            "rag_evaluation_result",
            "nl2sql_evaluation_result",
        ]:
            db.execute(text(f"DELETE FROM {table_name} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_evaluation_overview_rolls_up_all_quality_domains():
    tenant_id = "tenant_eval_overview_v1"
    user_id = "u_eval_overview"
    _cleanup_evaluation_overview_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            nl2sql_dataset = service.create_dataset(
                db, tenant_id=tenant_id, user_id=user_id, name="NL2SQL", description=None, target_type="nl2sql"
            )
            nl2sql_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=nl2sql_dataset["dataset_id"],
                title="SQL 成功",
                user_input="统计客户数量",
                expected_behavior="返回 SQL 查询结果",
                target_type="nl2sql",
                target_name="nl2sql.generate_sql",
            )
            service.create_nl2sql_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=nl2sql_case["case_id"],
                query_id="query_overview",
                generated_sql="SELECT 1",
                status="executed",
                row_count=1,
                elapsed_ms=10,
            )

            rag_dataset = service.create_dataset(
                db, tenant_id=tenant_id, user_id=user_id, name="RAG", description=None, target_type="rag"
            )
            rag_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=rag_dataset["dataset_id"],
                title="RAG 命中",
                user_input="平台能力有哪些？",
                expected_behavior="命中知识库章节",
                target_type="rag",
                target_name="rag.search",
            )
            service.create_rag_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=rag_case["case_id"],
                trace_id="trace_overview",
                top_k=5,
                hit_count=1,
                matched_rank=1,
                recall_hit=True,
                mrr_score=1,
                ndcg_score=1,
                elapsed_ms=20,
            )

            tool_dataset = service.create_dataset(
                db, tenant_id=tenant_id, user_id=user_id, name="Tool", description=None, target_type="tool"
            )
            tool_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=tool_dataset["dataset_id"],
                title="工具成功",
                user_input="查询数据",
                expected_behavior="工具成功返回",
                target_type="tool",
                target_name="data.query_sql",
            )
            service.create_tool_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=tool_case["case_id"],
                tool_name="data.query_sql",
                status="success",
                elapsed_ms=30,
            )

            agent_dataset = service.create_dataset(
                db, tenant_id=tenant_id, user_id=user_id, name="Agent", description=None, target_type="agent"
            )
            agent_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=agent_dataset["dataset_id"],
                title="Agent 完成",
                user_input="给出经营建议",
                expected_behavior="完成建议生成",
                target_type="agent",
                target_name="manager_decision",
            )
            service.create_agent_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=agent_case["case_id"],
                agent_type="manager_decision",
                agent_name="经营决策 Agent",
                status="completed",
                completion_score=1,
                elapsed_ms=40,
            )
            overview = service.summarize_evaluation_overview(db, tenant_id=tenant_id)

        assert overview["stage"] == "observability_evaluation_v1"
        assert overview["total_evaluation_count"] == 4
        assert overview["active_domain_count"] == 4
        assert {item["target_type"] for item in overview["domains"]} == {"nl2sql", "rag", "tool", "agent"}
        assert overview["summaries"]["nl2sql"]["success_rate"] == 1
        assert overview["summaries"]["rag"]["recall_at_k"] == 1
        assert overview["summaries"]["tool"]["success_rate"] == 1
        assert overview["summaries"]["agent"]["completion_rate"] == 1
    finally:
        _cleanup_evaluation_overview_fixture(tenant_id)
