from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_evaluation_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_evaluation_dataset_and_case_can_bind_target():
    tenant_id = "tenant_evaluation_case_v1"
    user_id = "u_eval_owner"
    _cleanup_evaluation_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            dataset = service.create_dataset(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                name="NL2SQL 基础准确率集",
                description="覆盖常见经营数据问答",
                target_type="nl2sql",
                metadata_json={"version": "v1"},
            )
            case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="查询高风险客户数量",
                user_input="本月高风险客户有多少个？",
                expected_behavior="生成只读 SQL，并返回高风险客户数量。",
                target_type="nl2sql",
                target_name="nl2sql.generate_sql",
                tags=["accuracy", "sql"],
                metadata_json={"difficulty": "basic"},
            )
            cases = service.list_cases(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
                target_type="nl2sql",
                target_name="nl2sql.generate_sql",
            )

        assert dataset["target_type"] == "nl2sql"
        assert dataset["metadata_json"]["version"] == "v1"
        assert case["dataset_id"] == dataset["dataset_id"]
        assert case["target_name"] == "nl2sql.generate_sql"
        assert case["tags"] == ["accuracy", "sql"]
        assert case["metadata_json"]["difficulty"] == "basic"
        assert len(cases) == 1
        assert cases[0]["case_id"] == case["case_id"]
    finally:
        _cleanup_evaluation_fixture(tenant_id)
