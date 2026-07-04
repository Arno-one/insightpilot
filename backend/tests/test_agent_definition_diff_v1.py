from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_definition_diff_reports_metadata_config_tool_and_memory_changes():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_diff_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_definition_diff_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            first = service.create_agent_definition(
                db,
                current_user,
                agent_code="diff_agent",
                agent_name="差异对比Agent v1",
                description="第一版",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "diff_graph_v1", "temperature": 0.1},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )
            second = service.clone_agent_definition(
                db,
                current_user,
                definition_id=first["definition_id"],
                agent_name="差异对比Agent v2",
                description="第二版",
                config_json={"entrypoint": "diff_graph_v2", "temperature": 0.2},
                tool_policy_json={"allowed_tools": ["data.query_sql", "data.analyze_business"]},
                memory_policy_json={"context_packet": True, "max_chars": 2400},
            )

            diff = service.diff_agent_definitions(
                db,
                current_user,
                base_definition_id=first["definition_id"],
                target_definition_id=second["definition_id"],
            )

        assert diff["summary"]["changed"] is True
        assert diff["summary"]["metadata_change_count"] >= 2
        assert diff["summary"]["config_change_count"] == 2
        assert diff["summary"]["tool_policy_change_count"] == 1
        assert diff["summary"]["memory_policy_change_count"] == 1
        assert "definition.agent_name" in diff["changed_paths"]
        assert "config_json.entrypoint" in diff["changed_paths"]
        assert "tool_policy_json.allowed_tools" in diff["changed_paths"]
        assert "memory_policy_json.max_chars" in diff["changed_paths"]
        assert diff["base_definition"]["version"] == 1
        assert diff["target_definition"]["version"] == 2
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_agent_definition_diff_returns_empty_changes_for_same_definition():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_empty_diff_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_definition_empty_diff_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                current_user,
                agent_code="empty_diff_agent",
                agent_name="无差异Agent",
                description="用于验证空差异",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={"entrypoint": "empty_diff_graph"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )

            diff = service.diff_agent_definitions(
                db,
                current_user,
                base_definition_id=created["definition_id"],
                target_definition_id=created["definition_id"],
            )

        # 中文注释：同一版本对比应返回稳定空差异，方便前端做无变化态展示。
        assert diff["summary"]["changed"] is False
        assert diff["summary"]["changed_count"] == 0
        assert diff["changed_paths"] == []
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
