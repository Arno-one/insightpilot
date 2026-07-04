from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_tool_policy_validation_reports_missing_and_permission_errors():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_tool_policy_validation_v1"
    creator = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_tool_policy_creator_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    reviewer_without_tool_permission = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_tool_policy_reviewer_v1",
        "permission_codes": [],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                creator,
                agent_code="tool_policy_validator",
                agent_name="工具策略校验Agent",
                description="用于验证工具策略质量门禁",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "tool_policy_validator_graph"},
                tool_policy_json={"allowed_tools": ["data.query_sql", "missing.tool"]},
                memory_policy_json={},
            )

            result = service.validate_agent_tool_policy(
                db,
                reviewer_without_tool_permission,
                definition_id=created["definition_id"],
            )

        assert result["valid"] is False
        assert result["summary"]["allowed_count"] == 2
        assert result["summary"]["blocked_count"] == 1
        assert result["summary"]["missing_count"] == 1
        assert {item["code"] for item in result["errors"]} == {
            "tool_not_registered",
            "tool_permission_missing",
        }
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_agent_tool_policy_validation_keeps_empty_allowed_tools_as_warning():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_empty_tool_policy_validation_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_empty_tool_policy_validation_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                current_user,
                agent_code="empty_tool_policy_validator",
                agent_name="空工具策略Agent",
                description="用于验证空工具策略提示",
                agent_type="quality_gate",
                runtime_type="chat",
                status="draft",
                version=1,
                config_json={},
                tool_policy_json={},
                memory_policy_json={},
            )

            result = service.validate_agent_tool_policy(db, current_user, definition_id=created["definition_id"])

        assert result["valid"] is True
        assert result["summary"]["warning_count"] == 1
        assert result["warnings"][0]["code"] == "empty_allowed_tools"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
