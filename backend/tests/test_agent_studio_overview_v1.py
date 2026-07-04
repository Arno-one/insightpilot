from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_studio_overview_summarizes_definitions_and_publish_audits():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_studio_overview_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_studio_overview_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            active = service.create_agent_definition(
                db,
                current_user,
                agent_code="overview_agent",
                agent_name="总览Agent v1",
                description="用于验证总览 active 统计",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "overview_graph_v1"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )
            draft = service.clone_agent_definition(
                db,
                current_user,
                definition_id=active["definition_id"],
                agent_name="总览Agent v2",
                config_json={"entrypoint": "overview_graph_v2"},
            )
            service.publish_agent_definition(db, current_user, definition_id=draft["definition_id"])
            invalid = service.create_agent_definition(
                db,
                current_user,
                agent_code="overview_block_agent",
                agent_name="总览阻断Agent",
                description="用于验证总览 blocked 统计",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )
            service.publish_agent_definition(db, current_user, definition_id=invalid["definition_id"])

            overview = service.summarize_agent_studio(db, current_user)

        assert overview["overview_version"] == "agent_studio_overview_v1"
        assert overview["definition_summary"]["total_count"] == 3
        assert overview["definition_summary"]["agent_code_count"] == 2
        assert overview["definition_summary"]["active_count"] == 1
        assert overview["definition_summary"]["disabled_count"] == 1
        assert overview["definition_summary"]["draft_count"] == 1
        assert overview["publish_audit_summary"]["total_count"] == 2
        assert overview["publish_audit_summary"]["published_count"] == 1
        assert overview["publish_audit_summary"]["blocked_count"] == 1
        assert len(overview["active_definitions"]) == 1
        assert overview["active_definitions"][0]["definition_id"] == draft["definition_id"]
        assert len(overview["recent_publish_audits"]) == 2
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
