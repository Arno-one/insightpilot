from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_publish_gate_blocks_definition_when_tool_policy_has_errors():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_publish_gate_block_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_publish_gate_block_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            draft = service.create_agent_definition(
                db,
                current_user,
                agent_code="blocked_publish_agent",
                agent_name="被阻断发布Agent",
                description="用于验证发布门禁阻断",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={"entrypoint": "blocked_publish_graph"},
                tool_policy_json={"allowed_tools": ["missing.tool"]},
                memory_policy_json={},
            )

            result = service.publish_agent_definition(db, current_user, definition_id=draft["definition_id"])
            loaded = service.get_agent_definition(db, current_user, definition_id=draft["definition_id"])

        assert result["published"] is False
        assert result["validation"]["valid"] is False
        assert result["validation"]["errors"][0]["code"] == "tool_not_registered"
        assert loaded["status"] == "draft"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_publish_gate_publishes_valid_definition_and_disables_previous_active_version():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_publish_gate_success_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_publish_gate_success_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            first = service.create_agent_definition(
                db,
                current_user,
                agent_code="publishable_agent",
                agent_name="可发布Agent v1",
                description="用于验证发布门禁成功链路",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "publishable_graph_v1"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )
            second = service.clone_agent_definition(
                db,
                current_user,
                definition_id=first["definition_id"],
                agent_name="可发布Agent v2",
                config_json={"entrypoint": "publishable_graph_v2"},
            )

            result = service.publish_agent_definition(db, current_user, definition_id=second["definition_id"])
            first_after_publish = service.get_agent_definition(db, current_user, definition_id=first["definition_id"])
            second_after_publish = service.get_agent_definition(db, current_user, definition_id=second["definition_id"])

        # 中文注释：发布门禁复用状态流转逻辑，确保新版本上线后旧 active 自动下线。
        assert result["published"] is True
        assert result["validation"]["valid"] is True
        assert first_after_publish["status"] == "disabled"
        assert second_after_publish["status"] == "active"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
