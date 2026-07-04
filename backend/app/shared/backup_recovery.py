from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

BackupMode = Literal["logical_dump", "event_log", "vector_snapshot", "artifact_export"]
CheckStatus = Literal["pass", "warn", "fail"]

BACKUP_RECOVERY_VERSION = "backup_recovery_v1"


@dataclass(frozen=True, slots=True)
class BackupDomain:
    """中文注释：一个备份域对应一组恢复时必须保持一致性的数据表。"""

    domain_id: str
    name: str
    tables: tuple[str, ...]
    backup_mode: BackupMode
    restore_order: int
    rpo_minutes: int
    rto_minutes: int
    retention_days: int
    tenant_scoped: bool
    verification_points: tuple[str, ...]

    def model_dump(self) -> dict:
        item = asdict(self)
        item["tables"] = list(self.tables)
        item["verification_points"] = list(self.verification_points)
        return item


@dataclass(frozen=True, slots=True)
class RecoveryGuardrail:
    """中文注释：恢复动作的门禁规则，V1 先固化为只读策略，避免误恢复覆盖生产数据。"""

    guardrail_id: str
    stage: str
    required: bool
    description: str

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecoveryRunbookStep:
    step_id: str
    title: str
    action: str
    expected_evidence: str

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BackupRecoveryCheck:
    check_id: str
    status: CheckStatus
    message: str
    recommendation: str

    def model_dump(self) -> dict:
        return asdict(self)


BACKUP_DOMAINS: tuple[BackupDomain, ...] = (
    BackupDomain(
        domain_id="tenant_identity",
        name="租户与权限基线",
        tables=("tenant", "sys_user", "sys_role", "sys_permission", "sys_user_role", "sys_role_permission"),
        backup_mode="logical_dump",
        restore_order=10,
        rpo_minutes=15,
        rto_minutes=60,
        retention_days=180,
        tenant_scoped=False,
        verification_points=("管理员账号可登录", "角色权限矩阵完整", "租户边界配置存在"),
    ),
    BackupDomain(
        domain_id="crm_operational",
        name="CRM 经营数据",
        tables=("crm_customer", "crm_contact", "crm_deal", "crm_follow_up_record"),
        backup_mode="logical_dump",
        restore_order=20,
        rpo_minutes=15,
        rto_minutes=90,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("客户数量与备份清单一致", "商机与联系人外键可追溯", "跟进记录时间线可查询"),
    ),
    BackupDomain(
        domain_id="risk_approval_task",
        name="风险、审批与任务闭环",
        tables=("customer_risk_snapshot", "risk_rule_config", "approval_record", "approval_task_event", "sales_task"),
        backup_mode="event_log",
        restore_order=30,
        rpo_minutes=15,
        rto_minutes=120,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("风险快照可按客户查询", "审批状态未丢失", "任务负责人和状态可恢复"),
    ),
    BackupDomain(
        domain_id="notification_calendar",
        name="通知与日程状态",
        tables=("internal_notification", "internal_calendar_event"),
        backup_mode="event_log",
        restore_order=40,
        rpo_minutes=30,
        rto_minutes=120,
        retention_days=180,
        tenant_scoped=True,
        verification_points=("失败通知可追溯", "日程占位不会重复触发真实外发", "投递重试状态存在"),
    ),
    BackupDomain(
        domain_id="agent_runtime",
        name="Agent Runtime 与会话轨迹",
        tables=(
            "agent_run",
            "agent_step",
            "agent_run_plan",
            "agent_run_plan_step",
            "agent_chat_session",
            "agent_chat_message",
            "agent_action_run",
            "agent_action_run_step",
        ),
        backup_mode="event_log",
        restore_order=50,
        rpo_minutes=15,
        rto_minutes=120,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("Trace 链路可打开", "失败恢复事件可聚合", "动作链不自动重放"),
    ),
    BackupDomain(
        domain_id="nl2sql_audit",
        name="NL2SQL 会话与审计",
        tables=("nl2sql_session", "nl2sql_message", "nl2sql_query_audit"),
        backup_mode="event_log",
        restore_order=60,
        rpo_minutes=15,
        rto_minutes=90,
        retention_days=180,
        tenant_scoped=True,
        verification_points=("查询审计 SQL 可追溯", "会话消息顺序完整", "租户过滤条件保留"),
    ),
    BackupDomain(
        domain_id="memory_governance",
        name="客户记忆与治理",
        tables=("customer_memory", "memory_update_trace", "memory_governance_state"),
        backup_mode="logical_dump",
        restore_order=70,
        rpo_minutes=30,
        rto_minutes=120,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("客户记忆状态可恢复", "治理开关不丢失", "更新 Trace 可审计"),
    ),
    BackupDomain(
        domain_id="rag_knowledge",
        name="RAG 知识库与检索轨迹",
        tables=("rag_document", "rag_chunk", "rag_qa_pair", "rag_ingest_job", "rag_retrieval_trace", "rag_retrieval_hit"),
        backup_mode="vector_snapshot",
        restore_order=80,
        rpo_minutes=60,
        rto_minutes=180,
        retention_days=180,
        tenant_scoped=True,
        verification_points=("文档与 chunk 数量一致", "向量索引可重建", "引用命中可追溯"),
    ),
    BackupDomain(
        domain_id="evaluation_observability",
        name="评测与可观测数据",
        tables=(
            "evaluation_dataset",
            "evaluation_case",
            "nl2sql_evaluation_result",
            "rag_evaluation_result",
            "tool_evaluation_result",
            "agent_evaluation_result",
            "llm_call_log",
        ),
        backup_mode="logical_dump",
        restore_order=90,
        rpo_minutes=60,
        rto_minutes=180,
        retention_days=180,
        tenant_scoped=True,
        verification_points=("评测集和用例可查询", "评测结果可聚合", "LLM 调用日志可审计"),
    ),
    BackupDomain(
        domain_id="agent_studio",
        name="Agent Studio 发布资产",
        tables=("agent_definition", "agent_definition_publish_audit"),
        backup_mode="artifact_export",
        restore_order=100,
        rpo_minutes=15,
        rto_minutes=120,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("已发布定义可回滚", "发布审计可查询", "版本号连续"),
    ),
    BackupDomain(
        domain_id="business_report",
        name="经营报告资产",
        tables=("business_report",),
        backup_mode="artifact_export",
        restore_order=110,
        rpo_minutes=60,
        rto_minutes=180,
        retention_days=365,
        tenant_scoped=True,
        verification_points=("日报/周报/月报可查询", "报告指标 JSON 可解析", "报告引用可回到客户"),
    ),
)

RECOVERY_GUARDRAILS: tuple[RecoveryGuardrail, ...] = (
    RecoveryGuardrail(
        guardrail_id="manual_approval_required",
        stage="before_restore",
        required=True,
        description="任何覆盖式恢复必须由系统管理员在工单中确认恢复窗口、租户范围和备份点。",
    ),
    RecoveryGuardrail(
        guardrail_id="dry_run_first",
        stage="before_restore",
        required=True,
        description="正式恢复前必须先在隔离环境执行 dry-run，并保存表数量、抽样校验和错误报告。",
    ),
    RecoveryGuardrail(
        guardrail_id="disable_side_effect_workers",
        stage="during_restore",
        required=True,
        description="恢复期间必须暂停通知、邮件、动作链等可能产生外发副作用的 Worker。",
    ),
    RecoveryGuardrail(
        guardrail_id="tenant_scope_lock",
        stage="during_restore",
        required=True,
        description="租户级恢复必须显式绑定 tenant_id，禁止无范围条件覆盖多租户数据。",
    ),
    RecoveryGuardrail(
        guardrail_id="post_restore_smoke_test",
        stage="after_restore",
        required=True,
        description="恢复后必须执行登录、客户查询、Agent Trace、NL2SQL 审计、RAG 检索等冒烟验证。",
    ),
)

RECOVERY_RUNBOOK: tuple[RecoveryRunbookStep, ...] = (
    RecoveryRunbookStep(
        step_id="freeze_writes",
        title="冻结写入与副作用 Worker",
        action="暂停异步队列、通知投递、邮件补发、动作链执行入口，只保留只读查询。",
        expected_evidence="发布系统记录冻结开始时间，队列消费数不再增长。",
    ),
    RecoveryRunbookStep(
        step_id="verify_backup_point",
        title="确认备份点与租户范围",
        action="核对备份清单、schema 版本、tenant_id 范围、RPO 时间点和操作人审批记录。",
        expected_evidence="备份清单哈希、审批工单和租户范围一致。",
    ),
    RecoveryRunbookStep(
        step_id="restore_schema",
        title="恢复结构与基础权限",
        action="先应用 Alembic/schema，再恢复 tenant 与 sys_* 权限基线。",
        expected_evidence="管理员账号可登录，权限矩阵校验通过。",
    ),
    RecoveryRunbookStep(
        step_id="restore_business_domains",
        title="按顺序恢复业务域",
        action="按 restore_order 恢复 CRM、风险审批任务、通知日程、Agent Runtime、NL2SQL、Memory、RAG 等域。",
        expected_evidence="每个域的表数量、关键抽样和外键关联校验通过。",
    ),
    RecoveryRunbookStep(
        step_id="rebuild_indexes",
        title="重建派生索引",
        action="重建 RAG 向量索引、统计缓存和只读检索索引，不重放外发动作。",
        expected_evidence="RAG 检索、报告查询和 Trace 页面冒烟通过。",
    ),
    RecoveryRunbookStep(
        step_id="resume_services",
        title="恢复服务与观察",
        action="逐步恢复 API、Worker 和通知通道，观察错误率、队列堆积、关键接口延迟。",
        expected_evidence="恢复后观察窗口内无新增阻断告警。",
    ),
)


def list_backup_domains() -> list[dict]:
    return [domain.model_dump() for domain in sorted(BACKUP_DOMAINS, key=lambda item: item.restore_order)]


def list_recovery_guardrails() -> list[dict]:
    return [guardrail.model_dump() for guardrail in RECOVERY_GUARDRAILS]


def list_recovery_runbook() -> list[dict]:
    return [step.model_dump() for step in RECOVERY_RUNBOOK]


def _status_counts(checks: list[BackupRecoveryCheck]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1
    return counts


def _build_checks(domains: tuple[BackupDomain, ...] = BACKUP_DOMAINS) -> list[BackupRecoveryCheck]:
    checks: list[BackupRecoveryCheck] = []
    all_tables = [table for domain in domains for table in domain.tables]
    restore_orders = [domain.restore_order for domain in domains]
    tenant_domain_count = sum(1 for domain in domains if domain.tenant_scoped)

    checks.append(
        BackupRecoveryCheck(
            check_id="critical_domain_coverage",
            status="pass" if len(domains) >= 8 and len(all_tables) >= 30 else "fail",
            message="关键业务域已纳入备份策略",
            recommendation="新增核心表时必须补充到 BACKUP_DOMAINS，并声明恢复顺序与校验点。",
        )
    )
    checks.append(
        BackupRecoveryCheck(
            check_id="restore_order_unique",
            status="pass" if len(restore_orders) == len(set(restore_orders)) else "fail",
            message="恢复顺序唯一且可排序",
            recommendation="每个备份域必须有唯一 restore_order，避免恢复脚本出现不确定顺序。",
        )
    )
    checks.append(
        BackupRecoveryCheck(
            check_id="tenant_scope_guarded",
            status="pass" if tenant_domain_count >= len(domains) - 1 else "fail",
            message="多租户业务域已声明租户范围",
            recommendation="除租户与全局权限基线外，业务数据域必须声明 tenant_scoped=True。",
        )
    )
    checks.append(
        BackupRecoveryCheck(
            check_id="destructive_restore_guarded",
            status="pass" if all(guardrail.required for guardrail in RECOVERY_GUARDRAILS) else "fail",
            message="覆盖式恢复已要求人工审批和 dry-run",
            recommendation="任何真实恢复执行器都必须先校验 guardrail，再允许进入写入阶段。",
        )
    )
    checks.append(
        BackupRecoveryCheck(
            check_id="external_storage_binding",
            status="warn",
            message="V1 未绑定对象存储或跨地域副本",
            recommendation="商用部署需在外部确认备份存储位置、加密方式、保留周期和恢复演练频率。",
        )
    )
    return checks


def build_backup_manifest(snapshot_id: str | None = None, *, generated_at: datetime | None = None) -> dict:
    """中文注释：生成只读备份清单模板，不读取真实数据，也不会触发任何外部写入。"""

    generated_at = generated_at or datetime.now(UTC)
    snapshot_id = snapshot_id or f"backup_manifest_{generated_at.strftime('%Y%m%d%H%M%S')}"
    domains = list_backup_domains()
    return {
        "manifest_version": BACKUP_RECOVERY_VERSION,
        "snapshot_id": snapshot_id,
        "generated_at": generated_at.isoformat(),
        "domain_count": len(domains),
        "table_count": sum(len(domain["tables"]) for domain in domains),
        "domains": domains,
        "checksum_policy": {
            "mode": "operator_generated",
            "required": True,
            "description": "真实备份产物必须由部署流水线生成文件哈希和表级计数，本模块只定义清单结构。",
        },
    }


def summarize_backup_recovery(generated_at: datetime | None = None) -> dict:
    checks = _build_checks()
    counts = _status_counts(checks)
    domains = list_backup_domains()
    manifest = build_backup_manifest(generated_at=generated_at)
    return {
        "plan_version": BACKUP_RECOVERY_VERSION,
        "overall_status": "blocked" if counts["fail"] else "ready",
        "domain_count": len(domains),
        "table_count": sum(len(domain["tables"]) for domain in domains),
        "check_counts": counts,
        "checks": [check.model_dump() for check in checks],
        "manifest": manifest,
        "guardrails": list_recovery_guardrails(),
        "runbook": list_recovery_runbook(),
        "execution_boundary": {
            "auto_backup_enabled": False,
            "auto_restore_enabled": False,
            "external_write_enabled": False,
            "description": "V1 只输出策略、清单和恢复演练步骤，不执行真实备份、删除、覆盖或外发动作。",
        },
    }
