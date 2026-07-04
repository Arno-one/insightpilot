from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.shared.backup_recovery import summarize_backup_recovery
from app.shared.deployment_readiness import summarize_deployment_readiness
from app.shared.enterprise_hardening import summarize_enterprise_hardening

GateSeverity = Literal["pass", "warning", "blocker"]

RELEASE_GATE_VERSION = "release_gate_checklist_v1"


@dataclass(frozen=True, slots=True)
class ReleaseGateItem:
    """中文注释：发布门禁项只输出判断和证据，不执行任何修复、恢复或外部动作。"""

    item_id: str
    category: str
    severity: GateSeverity
    title: str
    evidence: dict
    required_action: str
    source: str

    def model_dump(self) -> dict:
        return asdict(self)


def _deployment_warning_item(deployment: dict) -> ReleaseGateItem:
    warning_count = deployment["warning_count"]
    return ReleaseGateItem(
        item_id="deployment_warning_cleanup",
        category="deployment",
        severity="warning" if warning_count else "pass",
        title="部署 warning 收敛",
        evidence={
            "warning_count": warning_count,
            "check_counts": deployment["check_counts"],
        },
        required_action="生产发布前建议清理默认密钥、root 数据库账号、只读账号、Redis 密码等 warning。",
        source="deployment_readiness_v1",
    )


def _backup_storage_item(backup: dict) -> ReleaseGateItem:
    warning_count = backup["check_counts"].get("warn", 0)
    return ReleaseGateItem(
        item_id="backup_storage_confirmation",
        category="resilience",
        severity="warning" if warning_count else "pass",
        title="备份外部存储确认",
        evidence={
            "domain_count": backup["domain_count"],
            "table_count": backup["table_count"],
            "warning_count": warning_count,
            "auto_restore_enabled": backup["execution_boundary"]["auto_restore_enabled"],
            "external_write_enabled": backup["execution_boundary"]["external_write_enabled"],
        },
        required_action="生产发布前确认对象存储、加密方式、保留周期和恢复演练频率。",
        source="backup_recovery_v1",
    )


def summarize_release_gate(tenant_id: str | None = None) -> dict:
    """中文注释：聚合发布准入清单；只读判断，不自动发布、不自动修复。"""

    hardening = summarize_enterprise_hardening(tenant_id=tenant_id)
    deployment = summarize_deployment_readiness(public=True)
    backup = summarize_backup_recovery()

    items = [
        ReleaseGateItem(
            item_id="enterprise_hardening_blockers",
            category="hardening",
            severity="blocker" if hardening["status_counts"]["blocked"] else "pass",
            title="企业级硬化阻断项",
            evidence={
                "overall_status": hardening["overall_status"],
                "status_counts": hardening["status_counts"],
                "must_fix_before_production": hardening["stage_gate"]["must_fix_before_production"],
            },
            required_action="必须先修复所有 blocked 控制项，再进入生产发布。",
            source="enterprise_hardening_v1",
        ),
        ReleaseGateItem(
            item_id="deployment_blockers",
            category="deployment",
            severity="blocker" if deployment["blocking_count"] else "pass",
            title="部署阻断项",
            evidence={
                "blocking_count": deployment["blocking_count"],
                "check_counts": deployment["check_counts"],
            },
            required_action="必须清零部署阻断项，例如生产默认密钥、空数据库密码、空 Redis 密码等。",
            source="deployment_readiness_v1",
        ),
        _deployment_warning_item(deployment),
        _backup_storage_item(backup),
        ReleaseGateItem(
            item_id="external_action_boundary",
            category="compliance",
            severity="warning",
            title="真实外发与破坏性动作确认",
            evidence={
                "external_write_enabled": False,
                "auto_remediation_enabled": False,
                "auto_restore_enabled": False,
            },
            required_action="接入真实邮件、日历、对象存储、外部队列或恢复执行器前，必须按外发暂停场景确认。",
            source="loop_policy",
        ),
        ReleaseGateItem(
            item_id="audit_policy_present",
            category="audit",
            severity="pass",
            title="审计策略已挂载",
            evidence={"source": "audit_policy_v1", "required_for_high_risk": True},
            required_action="新增高风险动作时继续补充审计策略。",
            source="audit_policy_v1",
        ),
    ]

    severity_counts = {"pass": 0, "warning": 0, "blocker": 0}
    for item in items:
        severity_counts[item.severity] += 1

    if severity_counts["blocker"]:
        release_decision = "production_blocked"
    elif severity_counts["warning"]:
        release_decision = "pilot_allowed"
    else:
        release_decision = "production_candidate"

    return {
        "gate_version": RELEASE_GATE_VERSION,
        "release_decision": release_decision,
        "can_release_to_pilot": severity_counts["blocker"] == 0,
        "can_release_to_production": severity_counts["blocker"] == 0 and severity_counts["warning"] == 0,
        "item_count": len(items),
        "severity_counts": severity_counts,
        "items": [item.model_dump() for item in items],
        "manual_confirmation_required": [
            item.item_id for item in items if item.severity in {"warning", "blocker"}
        ],
        "execution_boundary": {
            "checklist_only": True,
            "external_write_enabled": False,
            "auto_release_enabled": False,
            "description": "V1 只输出发布准入判断，不自动发布、不自动修复、不触发真实外部动作。",
        },
    }
