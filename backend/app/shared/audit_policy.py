from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

AuditMode = Literal["required", "trace", "optional"]
AuditRiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class AuditPolicyRule:
    """中文注释：描述一类平台动作的审计要求，V1 先用代码配置承接企业级治理口径。"""

    rule_id: str
    event_scope: str
    resource_type: str
    action: str
    audit_mode: AuditMode
    risk_level: AuditRiskLevel
    retention_days: int
    required_fields: tuple[str, ...]
    description: str

    def model_dump(self) -> dict:
        item = asdict(self)
        item["required_fields"] = list(self.required_fields)
        return item


AUDIT_POLICY_VERSION = "audit_policy_v1"

AUDIT_POLICY_RULES: tuple[AuditPolicyRule, ...] = (
    AuditPolicyRule(
        rule_id="agent_definition_publish",
        event_scope="agent_studio",
        resource_type="agent_definition",
        action="publish",
        audit_mode="required",
        risk_level="high",
        retention_days=365,
        required_fields=("tenant_id", "definition_id", "agent_code", "version", "published_by_user_id"),
        description="Agent Definition 发布必须记录门禁结果和发布人。",
    ),
    AuditPolicyRule(
        rule_id="agent_definition_rollback",
        event_scope="agent_studio",
        resource_type="agent_definition",
        action="rollback",
        audit_mode="required",
        risk_level="high",
        retention_days=365,
        required_fields=("tenant_id", "definition_id", "agent_code", "version", "published_by_user_id"),
        description="Agent Definition 受控回滚必须记录门禁结果和操作人。",
    ),
    AuditPolicyRule(
        rule_id="mcp_high_risk_tool_execute",
        event_scope="mcp_gateway",
        resource_type="mcp_tool",
        action="execute_high_risk",
        audit_mode="required",
        risk_level="high",
        retention_days=365,
        required_fields=("tenant_id", "user_id", "run_id", "qualified_name", "request_payload", "trace_summary"),
        description="高风险 MCP 工具执行必须进入 Gateway 审计摘要。",
    ),
    AuditPolicyRule(
        rule_id="mail_mcp_retry",
        event_scope="mail_mcp",
        resource_type="notification_delivery",
        action="retry_failed_delivery",
        audit_mode="required",
        risk_level="high",
        retention_days=365,
        required_fields=("tenant_id", "user_id", "notification_id", "delivery_status", "retry_count"),
        description="邮件补发属于可能外发动作，必须记录投递状态和重试次数。",
    ),
    AuditPolicyRule(
        rule_id="nl2sql_query",
        event_scope="nl2sql",
        resource_type="query_audit",
        action="query",
        audit_mode="trace",
        risk_level="medium",
        retention_days=180,
        required_fields=("tenant_id", "user_id", "query_id", "question", "sql", "status"),
        description="NL2SQL 查询保留 SQL、问题和执行状态，便于数据访问复盘。",
    ),
    AuditPolicyRule(
        rule_id="memory_governance",
        event_scope="memory",
        resource_type="customer_memory",
        action="governance_change",
        audit_mode="required",
        risk_level="medium",
        retention_days=365,
        required_fields=("tenant_id", "user_id", "customer_id", "action", "reason"),
        description="客户记忆启停和刷新请求必须记录原因。",
    ),
)


def list_audit_policy_rules() -> list[dict]:
    return [rule.model_dump() for rule in AUDIT_POLICY_RULES]


def summarize_audit_policy() -> dict:
    rules = list_audit_policy_rules()
    mode_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for rule in rules:
        mode_counts[rule["audit_mode"]] = mode_counts.get(rule["audit_mode"], 0) + 1
        risk_counts[rule["risk_level"]] = risk_counts.get(rule["risk_level"], 0) + 1
    return {
        "policy_version": AUDIT_POLICY_VERSION,
        "rule_count": len(rules),
        "mode_counts": mode_counts,
        "risk_counts": risk_counts,
        "rules": rules,
    }
