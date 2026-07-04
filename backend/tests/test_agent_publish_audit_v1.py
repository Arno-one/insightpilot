from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_publish_gate_writes_audit_for_blocked_and_successful_publish_attempts():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_publish_audit_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_publish_audit_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            blocked_definition = service.create_agent_definition(
                db,
                current_user,
                agent_code="publish_audit_agent",
                agent_name="发布审计Agent v1",
                description="用于验证发布阻断审计",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )
            blocked_result = service.publish_agent_definition(
                db,
                current_user,
                definition_id=blocked_definition["definition_id"],
            )

            publishable_definition = service.create_agent_definition(
                db,
                current_user,
                agent_code="publish_audit_agent",
                agent_name="发布审计Agent v2",
                description="用于验证发布成功审计",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=2,
                config_json={"entrypoint": "publish_audit_graph"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )
            published_result = service.publish_agent_definition(
                db,
                current_user,
                definition_id=publishable_definition["definition_id"],
            )

            definition_audits = service.list_agent_publish_audits(
                db,
                current_user,
                definition_id=publishable_definition["definition_id"],
            )
            code_audits = service.list_agent_publish_audits(db, current_user, agent_code="publish_audit_agent")

        assert blocked_result["published"] is False
        assert blocked_result["publish_audit"]["publish_status"] == "blocked"
        assert blocked_result["publish_audit"]["error_count"] >= 1
        assert blocked_result["publish_audit"]["validation_json"]["valid"] is False

        assert published_result["published"] is True
        assert published_result["publish_audit"]["publish_status"] == "published"
        assert published_result["publish_audit"]["error_count"] == 0
        assert definition_audits[0]["audit_id"] == published_result["publish_audit"]["audit_id"]

        # 中文注释：按 agent_code 回看可以覆盖同一个 Agent 的多次发布尝试，便于后续审计页做时间线。
        assert len(code_audits) == 2
        assert {item["publish_status"] for item in code_audits} == {"blocked", "published"}
        assert all(item["published_by_user_id"] == current_user["user_id"] for item in code_audits)
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
