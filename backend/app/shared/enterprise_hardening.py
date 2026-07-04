from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.shared.audit_policy import summarize_audit_policy
from app.shared.backup_recovery import summarize_backup_recovery
from app.shared.deployment_readiness import summarize_deployment_readiness
from app.shared.event_bus import event_bus
from app.shared.runtime_queue import runtime_queue

HardeningStatus = Literal["ready", "warn", "blocked"]

ENTERPRISE_HARDENING_VERSION = "enterprise_hardening_v1"
PHASE_RANGE = "VNext-67..VNext-78"


@dataclass(frozen=True, slots=True)
class HardeningControl:
    """中文注释：阶段硬化控制项，聚合已完成能力的状态和可审计证据。"""

    control_id: str
    version: str
    category: str
    status: HardeningStatus
    evidence: dict
    source: str
    next_step: str

    def model_dump(self) -> dict:
        return asdict(self)


def _control_status_from_counts(check_counts: dict[str, int] | None = None, *, warning_count: int | None = None) -> HardeningStatus:
    if check_counts and check_counts.get("fail", 0) > 0:
        return "blocked"
    if warning_count is not None and warning_count > 0:
        return "warn"
    if check_counts and check_counts.get("warn", 0) > 0:
        return "warn"
    return "ready"


def _static_controls() -> list[HardeningControl]:
    return [
        HardeningControl(
            control_id="mcp_gateway_registry",
            version="mcp_gateway_registry_v1",
            category="mcp_gateway",
            status="ready",
            evidence={"scope": "共享 MCP Gateway 注册表", "external_write_enabled": False},
            source="VNext-67",
            next_step="接入真实外部 MCP Server 前，继续走外发场景确认。",
        ),
        HardeningControl(
            control_id="mcp_tool_permission",
            version="mcp_tool_permission_v1",
            category="mcp_gateway",
            status="ready",
            evidence={"scope": "工具级权限策略", "default_high_risk_boundary": "manual_approval"},
            source="VNext-68",
            next_step="新增高风险工具时必须声明权限和审批边界。",
        ),
        HardeningControl(
            control_id="mail_mcp_trace",
            version="mail_mcp_trace_v1",
            category="notification",
            status="ready",
            evidence={"scope": "邮件 MCP 审计 Trace", "retry_trace_required": True},
            source="VNext-69",
            next_step="真实邮件外发配置变更仍需按外发暂停规则确认。",
        ),
        HardeningControl(
            control_id="calendar_task_reservation",
            version="calendar_task_mcp_reservation_v1",
            category="mcp_gateway",
            status="ready",
            evidence={"scope": "Calendar / Task MCP 接口预留", "real_external_calendar_write": False},
            source="VNext-70",
            next_step="接入真实日历写入前必须补充外部集成审批。",
        ),
        HardeningControl(
            control_id="tenant_boundary",
            version="tenant_boundary_hardening_v1",
            category="security",
            status="ready",
            evidence={"scope": "多租户边界守卫", "tenant_scope_required": True},
            source="VNext-71",
            next_step="新增查询入口时继续复用租户边界校验。",
        ),
        HardeningControl(
            control_id="org_team_model",
            version="org_team_model_v1",
            category="rbac",
            status="ready",
            evidence={"scope": "组织团队模型只读接口", "permission": "system:rbac:manage"},
            source="VNext-72",
            next_step="进入复杂组织结构前再评估是否需要独立组织表。",
        ),
    ]


def _dynamic_controls(tenant_id: str | None = None) -> list[HardeningControl]:
    audit_policy = summarize_audit_policy()
    queue_overview = runtime_queue.overview(tenant_id=tenant_id)
    event_overview = event_bus.overview(tenant_id=tenant_id)
    deployment = summarize_deployment_readiness(public=True)
    backup = summarize_backup_recovery()

    return [
        HardeningControl(
            control_id="audit_policy",
            version=audit_policy["policy_version"],
            category="audit",
            status="ready" if audit_policy["rule_count"] > 0 else "blocked",
            evidence={
                "rule_count": audit_policy["rule_count"],
                "mode_counts": audit_policy["mode_counts"],
                "risk_counts": audit_policy["risk_counts"],
            },
            source="VNext-73",
            next_step="新增动作类型时补充审计策略并声明保留周期。",
        ),
        HardeningControl(
            control_id="runtime_queue",
            version=queue_overview["queue_version"],
            category="runtime",
            status="ready",
            evidence={
                "backend": queue_overview["backend"],
                "task_count": queue_overview["task_count"],
                "status_counts": queue_overview["status_counts"],
            },
            source="VNext-74",
            next_step="替换外部队列前保留当前队列语义和状态枚举。",
        ),
        HardeningControl(
            control_id="event_bus",
            version=event_overview["event_bus_version"],
            category="runtime",
            status="ready",
            evidence={
                "backend": event_overview["backend"],
                "event_count": event_overview["event_count"],
                "counts_by_type": event_overview["counts_by_type"],
                "counts_by_source": event_overview["counts_by_source"],
            },
            source="VNext-75",
            next_step="接入外部消息中间件前补充幂等键和重放策略。",
        ),
        HardeningControl(
            control_id="deployment_readiness",
            version=deployment["readiness_version"],
            category="deployment",
            status=_control_status_from_counts(deployment["check_counts"], warning_count=deployment["warning_count"]),
            evidence={
                "overall_status": deployment["overall_status"],
                "check_counts": deployment["check_counts"],
                "blocking_count": deployment["blocking_count"],
                "warning_count": deployment["warning_count"],
            },
            source="VNext-76",
            next_step="生产发布前清理所有阻断项，并尽量收敛 warning。",
        ),
        HardeningControl(
            control_id="backup_recovery",
            version=backup["plan_version"],
            category="resilience",
            status=_control_status_from_counts(backup["check_counts"]),
            evidence={
                "overall_status": backup["overall_status"],
                "domain_count": backup["domain_count"],
                "table_count": backup["table_count"],
                "check_counts": backup["check_counts"],
                "auto_restore_enabled": backup["execution_boundary"]["auto_restore_enabled"],
                "external_write_enabled": backup["execution_boundary"]["external_write_enabled"],
            },
            source="VNext-77",
            next_step="商用部署时确认对象存储、加密、保留周期和恢复演练频率。",
        ),
    ]


def summarize_enterprise_hardening(tenant_id: str | None = None) -> dict:
    """中文注释：聚合企业级硬化阶段报告；只读汇总，不输出事件 payload 或队列 payload。"""

    controls = [*_static_controls(), *_dynamic_controls(tenant_id=tenant_id)]
    status_counts = {"ready": 0, "warn": 0, "blocked": 0}
    for control in controls:
        status_counts[control.status] += 1

    if status_counts["blocked"]:
        overall_status = "blocked"
    elif status_counts["warn"]:
        overall_status = "ready_with_warnings"
    else:
        overall_status = "ready"

    return {
        "hardening_version": ENTERPRISE_HARDENING_VERSION,
        "phase_range": PHASE_RANGE,
        "overall_status": overall_status,
        "control_count": len(controls),
        "status_counts": status_counts,
        "controls": [control.model_dump() for control in controls],
        "stage_gate": {
            "can_enter_enterprise_pilot": status_counts["blocked"] == 0,
            "must_fix_before_production": [
                control.control_id for control in controls if control.status == "blocked"
            ],
            "should_fix_before_production": [
                control.control_id for control in controls if control.status == "warn"
            ],
        },
        "execution_boundary": {
            "report_only": True,
            "external_write_enabled": False,
            "auto_remediation_enabled": False,
            "description": "V1 阶段报告只做只读聚合，不自动修改配置、执行恢复、触发外部集成或产生费用。",
        },
    }
