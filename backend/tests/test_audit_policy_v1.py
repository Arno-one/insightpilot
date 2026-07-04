from app.modules.system.router import get_audit_policy
from app.shared.audit_policy import list_audit_policy_rules, summarize_audit_policy


def test_audit_policy_registry_exposes_required_enterprise_rules():
    policy = summarize_audit_policy()
    rules_by_id = {rule["rule_id"]: rule for rule in list_audit_policy_rules()}

    assert policy["policy_version"] == "audit_policy_v1"
    assert policy["rule_count"] == len(rules_by_id)
    assert policy["mode_counts"]["required"] >= 4
    assert policy["risk_counts"]["high"] >= 3

    publish_rule = rules_by_id["agent_definition_publish"]
    assert publish_rule["audit_mode"] == "required"
    assert publish_rule["risk_level"] == "high"
    assert "definition_id" in publish_rule["required_fields"]

    mcp_rule = rules_by_id["mcp_high_risk_tool_execute"]
    assert mcp_rule["event_scope"] == "mcp_gateway"
    assert "trace_summary" in mcp_rule["required_fields"]


def test_audit_policy_system_endpoint_returns_policy_summary():
    current_user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_admin_001",
        "permission_codes": ["system:rbac:manage"],
    }

    response = get_audit_policy(current_user=current_user)
    data = response["data"]

    assert response["total"] == data["rule_count"]
    assert data["policy_version"] == "audit_policy_v1"
    assert {rule["rule_id"] for rule in data["rules"]} >= {
        "agent_definition_publish",
        "mcp_high_risk_tool_execute",
        "mail_mcp_retry",
        "nl2sql_query",
    }
