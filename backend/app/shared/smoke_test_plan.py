from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SmokePriority = Literal["p0", "p1", "p2"]
SmokeMode = Literal["manual", "readonly_api", "visual_check"]

SMOKE_TEST_PLAN_VERSION = "operational_smoke_test_plan_v1"


@dataclass(frozen=True, slots=True)
class SmokeTestStep:
    """中文注释：企业试点冒烟测试步骤，只定义人工验证路径，不自动执行真实业务动作。"""

    step_id: str
    module: str
    title: str
    priority: SmokePriority
    mode: SmokeMode
    route_or_api: str
    operator_action: str
    expected_evidence: str
    rollback_hint: str
    side_effect_boundary: str

    def model_dump(self) -> dict:
        return asdict(self)


SMOKE_TEST_STEPS: tuple[SmokeTestStep, ...] = (
    SmokeTestStep(
        step_id="auth_login",
        module="认证",
        title="管理员与业务账号登录",
        priority="p0",
        mode="manual",
        route_or_api="/login, /api/auth/me",
        operator_action="使用管理员和一个业务账号分别登录，进入默认工作台后刷新当前用户信息。",
        expected_evidence="登录成功、顶部席位信息正确、/api/auth/me 返回租户和权限列表。",
        rollback_hint="若失败，检查账号状态、密码哈希、AUTH_SECRET_KEY 与数据库连接。",
        side_effect_boundary="只读身份校验，不创建业务数据。",
    ),
    SmokeTestStep(
        step_id="crm_customer_query",
        module="CRM",
        title="客户列表和客户详情查询",
        priority="p0",
        mode="visual_check",
        route_or_api="/customers, /api/crm/customers",
        operator_action="打开客户工作台，检索一个样例客户并进入详情。",
        expected_evidence="客户列表可加载，详情页能展示基础资料、风险、审批、任务和报告引用。",
        rollback_hint="若失败，检查 seed 数据、租户过滤条件和 CRM 查询权限。",
        side_effect_boundary="只读查询，不导入 CSV，不修改客户。",
    ),
    SmokeTestStep(
        step_id="agent_trace_review",
        module="Agent Trace",
        title="Agent 执行链路复盘",
        priority="p0",
        mode="visual_check",
        route_or_api="/agent-trace, /api/agent/runs",
        operator_action="打开 Agent 追踪页，选择最近一条运行记录并展开步骤详情。",
        expected_evidence="运行列表、步骤链、工具输出摘要和错误状态可见。",
        rollback_hint="若失败，检查 agent_run/agent_step 数据和 agent:log:read 权限。",
        side_effect_boundary="只读复盘，不重试 step，不触发 Agent 执行。",
    ),
    SmokeTestStep(
        step_id="nl2sql_audit_read",
        module="NL2SQL",
        title="智能问数与审计链路",
        priority="p1",
        mode="manual",
        route_or_api="/nl2sql, /api/nl2sql",
        operator_action="打开智能问数页面，查看历史或执行一条只读样例问题。",
        expected_evidence="SQL 生成过程有审计记录，结果表格可展示，租户过滤条件保留。",
        rollback_hint="若失败，检查模型 Key、只读数据库、nl2sql_query_audit 和查询权限。",
        side_effect_boundary="只允许只读 SQL；不得执行 UPDATE/DELETE/INSERT。",
    ),
    SmokeTestStep(
        step_id="rag_retrieval_quality",
        module="RAG",
        title="RAG 检索和引用证据",
        priority="p1",
        mode="manual",
        route_or_api="/rag-evaluation, /api/rag/search",
        operator_action="打开 RAG 评估页，查看检索评测或执行一条样例知识检索。",
        expected_evidence="检索结果包含命中文档、chunk、引用来源和评分摘要。",
        rollback_hint="若失败，检查 Milvus 配置、RAG 入库状态、Embedding 配置和 rag:ingest:run 权限。",
        side_effect_boundary="只读检索；不触发重新入库，不改写知识库。",
    ),
    SmokeTestStep(
        step_id="notification_status_review",
        module="通知",
        title="通知状态与失败投递复盘",
        priority="p1",
        mode="visual_check",
        route_or_api="/notifications, /api/notifications/failed",
        operator_action="打开通知中心，查看失败通知列表和单条投递详情。",
        expected_evidence="失败列表、投递状态、重试次数和错误摘要可见。",
        rollback_hint="若失败，检查 internal_notification 数据、登录权限和通知服务查询接口。",
        side_effect_boundary="不得点击真实补发或触发邮件重试；仅查看状态。",
    ),
    SmokeTestStep(
        step_id="approval_task_flow",
        module="审批与任务",
        title="审批任务和销售任务查询",
        priority="p0",
        mode="visual_check",
        route_or_api="/approvals, /tasks",
        operator_action="打开审批页和销售任务页，确认待办、状态、负责人和关联客户可见。",
        expected_evidence="审批记录、任务列表、状态筛选和负责人字段正常展示。",
        rollback_hint="若失败，检查 approval_record、sales_task、角色权限和租户过滤。",
        side_effect_boundary="不审批、不驳回、不批量改派任务。",
    ),
    SmokeTestStep(
        step_id="system_health_gate",
        module="系统健康",
        title="系统健康、发布门禁和备份恢复总览",
        priority="p0",
        mode="readonly_api",
        route_or_api="/system/health, /api/system/release-gate",
        operator_action="打开系统健康页，查看硬化报告、部署就绪、备份恢复和发布门禁四个维度。",
        expected_evidence="发布门禁为 pilot_allowed 或 production_candidate，0 blocker；warning 可解释。",
        rollback_hint="若失败，检查 system:rbac:manage 权限和系统管理接口。",
        side_effect_boundary="只读总览；不执行自动修复、真实备份或真实恢复。",
    ),
)


def list_smoke_test_steps() -> list[dict]:
    return [step.model_dump() for step in SMOKE_TEST_STEPS]


def summarize_smoke_test_plan() -> dict:
    steps = list_smoke_test_steps()
    priority_counts = {"p0": 0, "p1": 0, "p2": 0}
    mode_counts: dict[str, int] = {"manual": 0, "readonly_api": 0, "visual_check": 0}
    for step in steps:
        priority_counts[step["priority"]] += 1
        mode_counts[step["mode"]] += 1
    return {
        "plan_version": SMOKE_TEST_PLAN_VERSION,
        "overall_status": "ready",
        "step_count": len(steps),
        "priority_counts": priority_counts,
        "mode_counts": mode_counts,
        "steps": steps,
        "operator_recording": {
            "enabled": False,
            "mode": "frontend_draft_only",
            "description": "V1 仅预留人工记录入口，不写数据库、不上传附件、不触发外部系统。",
        },
        "execution_boundary": {
            "auto_execute_enabled": False,
            "external_write_enabled": False,
            "data_mutation_enabled": False,
            "description": "V1 只输出企业试点冒烟计划，不自动执行接口、不修改业务数据、不产生外发动作。",
        },
    }
