from app.core.database import SessionLocal
from app.modules.system.router import get_team_model


def test_org_team_model_derives_scope_from_existing_roles_and_permissions():
    current_user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_admin_001",
        "permission_codes": ["system:rbac:manage"],
    }

    with SessionLocal() as db:
        response = get_team_model(current_user=current_user, db=db)

    data = response["data"]
    users_by_username = {user["username"]: user for user in data["users"]}

    assert data["model_version"] == "org_team_model_v1"
    assert data["tenant_id"] == "demo_tenant"
    assert data["user_count"] >= 4
    assert users_by_username["admin"]["team_scope"] == "tenant_admin"
    assert users_by_username["owner"]["team_scope"] == "tenant_admin"
    assert users_by_username["manager"]["team_scope"] == "team_manager"
    assert users_by_username["sales01"]["team_scope"] == "team_member"
    assert users_by_username["owner"]["crm_visibility"] == "all"
    assert users_by_username["manager"]["crm_visibility"] == "team"
    assert users_by_username["sales01"]["crm_visibility"] == "self"
    assert users_by_username["manager"]["can_review_approval"] is True
    assert users_by_username["admin"]["can_manage_system"] is True


def test_org_team_model_is_limited_to_current_tenant():
    current_user = {
        "tenant_id": "tenant_without_team_users",
        "user_id": "u_empty_admin",
        "permission_codes": ["system:rbac:manage"],
    }

    with SessionLocal() as db:
        response = get_team_model(current_user=current_user, db=db)

    assert response["data"]["tenant_id"] == "tenant_without_team_users"
    assert response["data"]["user_count"] == 0
    assert response["data"]["users"] == []
