from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_manifest_packages_runtime_tools_memory_and_governance():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_manifest_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_manifest_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                current_user,
                agent_code="manifest_sales_advisor",
                agent_name="Manifest 销售顾问",
                description="用于验证运行时配置包",
                agent_type="sales",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "sales_advisor_graph", "temperature": 0.2},
                tool_policy_json={
                    "allowed_tools": ["data.query_sql", "missing.tool"],
                    "router": "agent_chat_tool_router_v1",
                },
                memory_policy_json={"context_packet": True, "max_chars": 1800},
            )

            manifest_by_id = service.build_agent_manifest(
                db,
                current_user,
                definition_id=created["definition_id"],
            )
            manifest_by_code = service.build_agent_manifest(
                db,
                current_user,
                agent_code="manifest_sales_advisor",
            )

        assert manifest_by_id["manifest_version"] == "agent_manifest_v1"
        assert manifest_by_id["definition"]["definition_id"] == created["definition_id"]
        assert manifest_by_id["definition"]["status"] == "active"
        assert manifest_by_id["runtime"]["entrypoint"] == "sales_advisor_graph"
        assert manifest_by_id["runtime"]["config"]["temperature"] == 0.2

        tool_manifest = manifest_by_id["tool_manifest"]
        assert tool_manifest["allowed_tools"] == ["data.query_sql", "missing.tool"]
        assert [item["name"] for item in tool_manifest["enabled_tools"]] == ["data.query_sql"]
        assert tool_manifest["missing_tools"] == ["missing.tool"]
        assert tool_manifest["registry_tool_count"] >= 1

        # 中文注释：记忆策略进入 Manifest 后，Runtime 后续可以直接按策略生成上下文包。
        assert manifest_by_id["memory_manifest"]["context_packet"] is True
        assert manifest_by_id["memory_manifest"]["max_chars"] == 1800
        assert manifest_by_id["governance"]["single_active_version"] is True
        assert manifest_by_code["definition"]["definition_id"] == created["definition_id"]
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
