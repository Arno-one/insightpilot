import pytest

from app.core.database import SessionLocal
from app.modules.agent_studio import service
from app.shared.tenant_boundary import require_current_tenant, tenant_params
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_tenant_boundary_guard_allows_current_tenant_and_builds_params():
    current_user = {"tenant_id": "tenant_guard_v1", "user_id": "user_guard_v1"}

    require_current_tenant(current_user, "tenant_guard_v1", resource_name="测试资源")
    params = tenant_params(current_user, definition_id="def_guard_v1")

    assert params == {"tenant_id": "tenant_guard_v1", "definition_id": "def_guard_v1"}


def test_tenant_boundary_guard_hides_cross_tenant_resource():
    current_user = {"tenant_id": "tenant_guard_a", "user_id": "user_guard_v1"}

    with pytest.raises(ValueError, match="测试资源 不存在或无权访问"):
        require_current_tenant(current_user, "tenant_guard_b", resource_name="测试资源")


def test_agent_definition_get_rejects_cross_tenant_definition_id():
    _ensure_agent_definition_table_exists()
    tenant_a = "tenant_boundary_agent_a"
    tenant_b = "tenant_boundary_agent_b"
    current_user_a = {
        "tenant_id": tenant_a,
        "user_id": "user_boundary_a",
        "permission_codes": ["crm:customer:read:self"],
    }
    current_user_b = {
        "tenant_id": tenant_b,
        "user_id": "user_boundary_b",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_a)
    _cleanup_agent_definition_fixture(tenant_b)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                current_user_a,
                agent_code="tenant_boundary_agent",
                agent_name="租户边界 Agent",
                description="用于验证跨租户不可见",
                agent_type="security",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={"entrypoint": "tenant_boundary_graph"},
                tool_policy_json={"allowed_tools": ["crm.search_customer"]},
                memory_policy_json={"context_packet": False},
            )
            loaded = service.get_agent_definition(db, current_user_a, definition_id=created["definition_id"])

            with pytest.raises(ValueError, match="Agent Definition 不存在"):
                service.get_agent_definition(db, current_user_b, definition_id=created["definition_id"])

        assert loaded["definition_id"] == created["definition_id"]
        assert "_tenant_id" not in loaded
    finally:
        _cleanup_agent_definition_fixture(tenant_a)
        _cleanup_agent_definition_fixture(tenant_b)
