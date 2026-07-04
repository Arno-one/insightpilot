import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.agent.memory_service import (
    build_customer_memory_snapshot,
    load_customer_memory_map,
    upsert_customer_memory,
)
from app.modules.agent.platform import MCPGateway, MCPServerAdapter, MCPToolDefinition, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.llm.client import RiskAdvice, generate_risk_advice, plan_risk_tool_calls, review_risk_tool_results
from app.modules.risk.rules import calculate_risk_score
from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event

logger = logging.getLogger(__name__)


class RiskCandidate(TypedDict):
    customer: dict[str, Any]
    deal: dict[str, Any] | None
    risk_result: dict[str, Any]


class RiskAnalysisState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    customer_id: str
    run_id: str
    started_at: datetime
    started_ts: float
    customers: list[dict[str, Any]]
    deals_by_customer: dict[str, dict[str, Any]]
    memories_by_customer: dict[str, dict[str, Any]]
    risk_candidates: list[RiskCandidate]
    planned_actions: list[dict[str, Any]]
    executed_actions: list[dict[str, Any]]
    reviewed_actions: list[dict[str, Any]]
    created: list[dict[str, Any]]
    memory_updates: list[dict[str, Any]]
    status: str
    output: dict[str, Any]


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dumps(data: dict[str, Any] | list[Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _insert_step(
    db: Session,
    tenant_id: str,
    run_id: str,
    node_name: str,
    status: str,
    started: float,
    output: dict[str, Any],
    tool_name: str | None = None,
    error_message: str | None = None,
):
    """记录 Agent 节点执行情况，前端 Trace 直接复用这里的结果。"""
    finished = time.time()
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, error_message, started_at, finished_at, duration_ms
            )
            VALUES (
              :tenant_id, :step_id, :run_id, :node_name, :tool_name, :input_json, :output_json,
              :status, :error_message, :started_at, :finished_at, :duration_ms
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_id": new_id("step"),
            "run_id": run_id,
            "node_name": node_name,
            "tool_name": tool_name,
            "input_json": _dumps({}),
            "output_json": _dumps(output),
            "status": status,
            "error_message": error_message,
            "started_at": datetime.fromtimestamp(started),
            "finished_at": datetime.fromtimestamp(finished),
            "duration_ms": int((finished - started) * 1000),
        },
    )


def _load_customers(db: Session, tenant_id: str, customer_id: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"tenant_id": tenant_id}
    customer_filter = ""
    if customer_id:
        customer_filter = "AND customer_id = :customer_id"
        params["customer_id"] = customer_id
    rows = db.execute(
        text(
            f"""
            SELECT *
            FROM crm_customer
            WHERE tenant_id = :tenant_id
              AND lifecycle_stage NOT IN ('won', 'lost')
              {customer_filter}
            ORDER BY updated_at DESC
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def _load_deals_by_customer(db: Session, tenant_id: str, customer_id: str | None = None) -> dict[str, dict[str, Any]]:
    params: dict[str, Any] = {"tenant_id": tenant_id}
    customer_filter = ""
    if customer_id:
        customer_filter = "AND customer_id = :customer_id"
        params["customer_id"] = customer_id
    rows = db.execute(
        text(
            f"""
            SELECT *
            FROM crm_deal
            WHERE tenant_id = :tenant_id
              AND close_result = 'open'
              {customer_filter}
            ORDER BY updated_at DESC
            """
        ),
        params,
    ).mappings().all()
    deals: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        deals.setdefault(item["customer_id"], item)
    return deals


def _approval_due_policy(risk_level: str) -> str:
    return "tomorrow" if risk_level == "high" else "in_2_days"


def _build_rag_question(customer: dict[str, Any], deal: dict[str, Any] | None, risk_result: dict[str, Any]) -> str:
    """把结构化风险结果改写成自然语言问题，避免把整包 JSON 直接扔给向量库。"""
    rule_names = "、".join(hit["rule_name"] for hit in risk_result["rule_hits"]) or "暂无明显规则命中"
    parts = [
        f"客户{customer.get('customer_name', customer.get('customer_id'))}当前风险等级为{risk_result['risk_level']}，命中规则：{rule_names}。",
        "请检索适合的销售SOP、报价跟进策略、异议处理话术和下一步行动建议。",
    ]
    if deal:
        parts.append(f"商机阶段为{deal.get('stage')}，金额为{deal.get('amount')}。")
    if customer.get("competitor_involved"):
        parts.append("客户已出现竞品介入，需要竞品异议处理建议。")
    if customer.get("last_sentiment") == "negative":
        parts.append("客户最近沟通情绪偏负面，需要更稳妥的话术。")
    return " ".join(parts)


def _retrieve_rag_context(
    tenant_id: str,
    user_id: str,
    customer: dict[str, Any],
    deal: dict[str, Any] | None,
    risk_result: dict[str, Any],
) -> dict[str, Any]:
    """检索销售知识库；RAG 失败时只降级，不阻断风险识别和审批草稿生成。"""
    question = _build_rag_question(customer, deal, risk_result)
    try:
        # 中文注释：延迟导入 RAG，避免 Worker 启动时因为向量库依赖导致整个队列不可用。
        from app.modules.rag.retrieval_service import search_knowledge

        response = search_knowledge(
            tenant_id=tenant_id,
            user_id=user_id,
            question=question,
            top_k=3,
            enable_rerank=True,
        )
        return {
            "status": "success",
            "question": question,
            "trace_id": response.trace_id,
            "hit_count": len(response.hits),
            "context": response.answer_context,
            "citations": [citation.model_dump() for citation in response.citations],
            "sources": [
                {
                    "citation_id": hit.citation_id,
                    "source_type": hit.source_type,
                    "doc_id": hit.doc_id,
                    "section_id": hit.section_id,
                    "rank_no": hit.rank_no,
                }
                for hit in response.hits
            ],
        }
    except Exception as exc:
        logger.warning("RAG 检索失败，风险扫描自动降级: customer_id=%s, error=%s", customer.get("customer_id"), exc)
        return {
            "status": "failed",
            "question": question,
            "trace_id": None,
            "hit_count": 0,
            "context": "",
            "citations": [],
            "sources": [],
            "error": str(exc),
        }


def _with_rag_evidence(risk_result: dict[str, Any], rag_result: dict[str, Any]) -> dict[str, Any]:
    """把 RAG 元信息写回风险证据，方便后续审计和前端追踪。"""
    evidence = {
        **risk_result.get("evidence", {}),
        "rag_trace_id": rag_result.get("trace_id"),
        "rag_hit_count": rag_result.get("hit_count", 0),
        "rag_status": rag_result.get("status"),
        "rag_sources": rag_result.get("sources", []),
        "rag_citations": rag_result.get("citations", []),
    }
    if rag_result.get("error"):
        evidence["rag_error"] = rag_result["error"][:500]
    return {**risk_result, "evidence": evidence}


def _build_additional_advice_context(payload: dict[str, Any]) -> str:
    """把内部工具补充到的客户经营上下文压缩成文本，供建议生成阶段直接消费。"""
    parts: list[str] = []

    customer_memory = payload.get("customer_memory")
    if isinstance(customer_memory, dict) and customer_memory.get("summary_text"):
        parts.append(f"客户长期记忆：{str(customer_memory.get('summary_text'))[:240]}")

    customer_detail = payload.get("customer_detail")
    if isinstance(customer_detail, dict):
        follow_ups = customer_detail.get("follow_ups", [])
        approvals = customer_detail.get("approvals", [])
        tasks = customer_detail.get("tasks", [])
        report_refs = customer_detail.get("report_refs", [])
        risk_snapshots = customer_detail.get("risk_snapshots", [])
        if follow_ups:
            latest_follow_up = follow_ups[0]
            parts.append(
                "最近跟进："
                f"{latest_follow_up.get('follow_up_type', 'unknown')}，"
                f"时间 {latest_follow_up.get('occurred_at', 'unknown')}。"
            )
        if approvals:
            pending_approvals = sum(1 for item in approvals if item.get("status") == "pending")
            parts.append(f"客户近期待审批草稿 {pending_approvals} 条，审批记录总计 {len(approvals)} 条。")
        if tasks:
            active_tasks = sum(1 for item in tasks if item.get("status") in {"pending", "in_progress"})
            parts.append(f"客户当前活跃任务 {active_tasks} 条，任务记录总计 {len(tasks)} 条。")
        if risk_snapshots:
            latest_snapshot = risk_snapshots[0]
            parts.append(
                f"最近风险快照等级 {latest_snapshot.get('risk_level', 'unknown')}，"
                f"分数 {latest_snapshot.get('risk_score', 'unknown')}。"
            )
        if report_refs:
            latest_report = report_refs[0]
            parts.append(
                f"最近关联报告 {latest_report.get('report_type', 'unknown')} / "
                f"{latest_report.get('report_date', 'unknown')}。"
            )

    report_items = payload.get("related_reports")
    if isinstance(report_items, list) and report_items:
        latest_report = report_items[0]
        parts.append(
            "经营报告摘要："
            f"{str(latest_report.get('summary') or '')[:120]}"
        )

    return "\n".join(part for part in parts if part).strip()


def _build_review_driven_approval_payload(
    customer: dict[str, Any],
    risk_result: dict[str, Any],
    advice: RiskAdvice,
    *,
    rag_result: dict[str, Any],
    review_data: dict[str, Any] | None = None,
    related_reports: list[dict[str, Any]] | None = None,
    tool_executions: list[dict[str, Any]] | None = None,
    context_summary: str = "",
) -> dict[str, Any]:
    """把 Reviewer 结论和执行证据写进审批草稿，方便人工审核直接看到 Agent 判断依据。"""
    tool_executions = tool_executions or []
    related_reports = related_reports or []

    payload = {
        "task_type": advice.task_type,
        "title": advice.task_title,
        "assignee_user_id": customer["owner_user_id"],
        "priority": advice.priority,
        "due_at": _approval_due_policy(risk_result["risk_level"]),
        "recommended_script": advice.recommended_script,
        "description": advice.suggestion,
        "agent_review": {
            "approved": bool((review_data or {}).get("approved", True)),
            "summary": (review_data or {}).get("summary", ""),
            "review_note": (review_data or {}).get("review_note", ""),
            "evidence_used": list((review_data or {}).get("evidence_used", [])),
        },
        "agent_context": {
            "risk_score": risk_result.get("risk_score"),
            "risk_level": risk_result.get("risk_level"),
            "rag_status": rag_result.get("status"),
            "rag_trace_id": rag_result.get("trace_id"),
            "rag_hit_count": rag_result.get("hit_count", 0),
            "report_count": len(related_reports),
            "tool_names": [item.get("tool_name") for item in tool_executions if item.get("tool_name")],
            "context_summary": context_summary,
        },
    }
    return payload


def _insert_risk_and_approval(
    db: Session,
    tenant_id: str,
    run_id: str,
    requester_user_id: str,
    customer: dict[str, Any],
    deal: dict[str, Any] | None,
    risk_result: dict[str, Any],
    rag_result: dict[str, Any],
    advice_data: dict[str, Any] | None = None,
    review_data: dict[str, Any] | None = None,
    related_reports: list[dict[str, Any]] | None = None,
    tool_executions: list[dict[str, Any]] | None = None,
    context_summary: str = "",
) -> dict[str, Any]:
    enriched_risk_result = _with_rag_evidence(risk_result, rag_result)
    if advice_data:
        advice = RiskAdvice.model_validate(advice_data)
    else:
        advice = generate_risk_advice(customer, deal, enriched_risk_result, rag_context=rag_result.get("context", ""))
    risk_snapshot_id = new_id("risk")
    approval_id = new_id("appr")

    suggested_task = _build_review_driven_approval_payload(
        customer,
        enriched_risk_result,
        advice,
        rag_result=rag_result,
        review_data=review_data,
        related_reports=related_reports,
        tool_executions=tool_executions,
        context_summary=context_summary,
    )

    db.execute(
        text(
            """
            INSERT INTO customer_risk_snapshot (
              tenant_id, risk_snapshot_id, customer_id, deal_id, owner_user_id, risk_score,
              risk_level, rule_hits_json, evidence_json, llm_reason, llm_suggestion,
              suggested_task_json, status, generated_by_run_id
            )
            VALUES (
              :tenant_id, :risk_snapshot_id, :customer_id, :deal_id, :owner_user_id, :risk_score,
              :risk_level, :rule_hits_json, :evidence_json, :llm_reason, :llm_suggestion,
              :suggested_task_json, 'pending_review', :generated_by_run_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "risk_snapshot_id": risk_snapshot_id,
            "customer_id": customer["customer_id"],
            "deal_id": deal["deal_id"] if deal else None,
            "owner_user_id": customer["owner_user_id"],
            "risk_score": enriched_risk_result["risk_score"],
            "risk_level": enriched_risk_result["risk_level"],
            "rule_hits_json": _dumps(enriched_risk_result["rule_hits"]),
            "evidence_json": _dumps(enriched_risk_result["evidence"]),
            "llm_reason": advice.reason,
            "llm_suggestion": advice.suggestion,
            "suggested_task_json": _dumps(suggested_task),
            "generated_by_run_id": run_id,
        },
    )

    db.execute(
        text(
            """
            INSERT INTO approval_record (
              tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
              proposed_payload_json, status, requested_by_user_id
            )
            VALUES (
              :tenant_id, :approval_id, 'agent_task_draft', :run_id, :risk_snapshot_id, :customer_id,
              :proposed_payload_json, 'pending', :requested_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "approval_id": approval_id,
            "run_id": run_id,
            "risk_snapshot_id": risk_snapshot_id,
            "customer_id": customer["customer_id"],
            "proposed_payload_json": _dumps(suggested_task),
            "requested_by_user_id": requester_user_id,
        },
    )
    log_workflow_event(
        db,
        tenant_id=tenant_id,
        entity_type="approval",
        entity_id=approval_id,
        approval_id=approval_id,
        customer_id=customer["customer_id"],
        risk_snapshot_id=risk_snapshot_id,
        action_type="approval_created",
        operator_user_id=requester_user_id,
        note="AI 风险建议已进入人工审批队列",
        detail={
            "approval_type": "agent_task_draft",
            "title": advice.task_title,
            "priority": advice.priority,
            "assignee_user_id": customer["owner_user_id"],
        },
    )

    return {
        "risk_snapshot_id": risk_snapshot_id,
        "approval_id": approval_id,
        "customer_id": customer["customer_id"],
        "risk_score": enriched_risk_result["risk_score"],
        "risk_level": enriched_risk_result["risk_level"],
        "rag_trace_id": rag_result.get("trace_id"),
        "rag_hit_count": rag_result.get("hit_count", 0),
        "review_summary": (review_data or {}).get("summary", ""),
        "evidence_used": list((review_data or {}).get("evidence_used", [])),
        "proposed_payload_json": suggested_task,
    }


def _build_risk_mcp_gateway() -> MCPGateway:
    """中文注释：在共享 MCP Gateway 上继续挂载 Risk Agent 运行时专属工具。"""

    def rag_retrieval_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        return _retrieve_rag_context(
            context.tenant_id,
            context.user_id,
            payload["customer"],
            payload.get("deal"),
            payload["risk_result"],
        )

    def risk_advice_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        rag_result = payload.get(
            "rag_result",
            {
                "status": "skipped",
                "trace_id": None,
                "hit_count": 0,
                "context": "",
                "sources": [],
            },
        )
        additional_context = _build_additional_advice_context(payload)
        rag_context = rag_result.get("context", "")
        merged_context = "\n\n".join(part for part in [rag_context, additional_context] if part).strip()
        enriched_risk_result = _with_rag_evidence(payload["risk_result"], rag_result)
        advice = generate_risk_advice(
            payload["customer"],
            payload.get("deal"),
            enriched_risk_result,
            rag_context=merged_context,
            customer_memory=payload.get("customer_memory"),
        )
        return {
            "advice": advice.model_dump(),
            "rag_status": rag_result.get("status"),
            "rag_hit_count": rag_result.get("hit_count", 0),
            "context_summary": additional_context,
        }

    def create_risk_draft_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        return _insert_risk_and_approval(
            context.db,
            context.tenant_id,
            context.run_id,
            context.user_id,
            payload["customer"],
            payload.get("deal"),
            payload["risk_result"],
            payload.get(
                "rag_result",
                {
                    "status": "skipped",
                    "trace_id": None,
                    "hit_count": 0,
                    "context": "",
                    "sources": [],
                },
            ),
            advice_data=payload.get("advice"),
            review_data=payload.get("review"),
            related_reports=payload.get("related_reports"),
            tool_executions=payload.get("tool_executions"),
            context_summary=payload.get("context_summary", ""),
        )

    gateway = build_shared_mcp_gateway()
    gateway.register_server(
        MCPServerAdapter(
            "rag",
            "RAG MCP",
            [
                MCPToolDefinition(
                    server_name="rag",
                    tool_name="retrieve_sales_context",
                    description="从销售知识库检索当前客户风险处置所需的 SOP、话术和案例上下文。",
                    handler=rag_retrieval_tool,
                )
            ],
        )
    )
    gateway.register_server(
        MCPServerAdapter(
            "risk",
            "Risk MCP",
            [
                MCPToolDefinition(
                    server_name="risk",
                    tool_name="generate_advice",
                    description="基于规则命中和知识上下文生成结构化风险建议。",
                    handler=risk_advice_tool,
                )
            ],
        )
    )
    gateway.register_server(
        MCPServerAdapter(
            "approval",
            "Approval MCP",
            [
                MCPToolDefinition(
                    server_name="approval",
                    tool_name="create_risk_draft",
                    description="把已通过复核的风险建议写入风险快照和人工审批草稿。",
                    handler=create_risk_draft_tool,
                )
            ],
        )
    )
    return gateway

    return InternalToolRegistry(
        [
            *build_shared_internal_tools(),
            ToolDefinition(
                name="rag.retrieve_sales_context",
                description="从销售知识库检索当前客户风险处置所需的 SOP、话术和案例上下文。",
                handler=rag_retrieval_tool,
            ),
            ToolDefinition(
                name="risk.generate_advice",
                description="基于规则命中和知识上下文生成结构化风险建议。",
                handler=risk_advice_tool,
            ),
            ToolDefinition(
                name="approval.create_risk_draft",
                description="把已通过复核的风险建议写入风险快照和人工审批草稿。",
                handler=create_risk_draft_tool,
            ),
        ]
    )


def _update_failed_run(db: Session, tenant_id: str, run_id: str, exc: Exception, started_ts: float):
    db.execute(
        text(
            """
            UPDATE agent_run
            SET status = 'failed',
                error_message = :error_message,
                finished_at = :finished_at,
                total_duration_ms = :total_duration_ms
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "error_message": str(exc),
            "finished_at": datetime.now(),
            "total_duration_ms": int((time.time() - started_ts) * 1000),
        },
    )


def build_risk_analysis_graph(db: Session):
    """构建风险扫描图，把工具发现与执行统一切到 MCP Gateway V1。"""
    tool_gateway = _build_risk_mcp_gateway()

    def run_node(
        state: RiskAnalysisState,
        node_name: str,
        tool_name: str | None,
        handler: Callable[[RiskAnalysisState], tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        started = time.time()
        try:
            output, updates = handler(state)
            _insert_step(db, state["tenant_id"], state["run_id"], node_name, "success", started, output, tool_name)
            return updates
        except Exception as exc:
            _insert_step(
                db,
                state["tenant_id"],
                state["run_id"],
                node_name,
                "failed",
                started,
                {"error": str(exc)[:500]},
                tool_name,
                error_message=str(exc)[:1000],
            )
            raise

    def load_crm_data(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            customer_id = current_state.get("customer_id")
            customers = _load_customers(db, current_state["tenant_id"], customer_id=customer_id)
            deals_by_customer = _load_deals_by_customer(db, current_state["tenant_id"], customer_id=customer_id)
            return (
                {"customer_count": len(customers), "deal_count": len(deals_by_customer)},
                {"customers": customers, "deals_by_customer": deals_by_customer},
            )

        return run_node(state, "load_crm_data", "crm_query_tool", handler)

    def load_customer_memory(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            customers = current_state.get("customers", [])
            customer_ids = [item["customer_id"] for item in customers if item.get("customer_id")]
            memories_by_customer = load_customer_memory_map(db, current_state["tenant_id"], customer_ids)
            hit_count = sum(1 for customer_id in customer_ids if customer_id in memories_by_customer)
            return (
                {
                    "customer_count": len(customer_ids),
                    "memory_hit_count": hit_count,
                    "memory_miss_count": max(len(customer_ids) - hit_count, 0),
                    "memory_preview": [
                        {
                            "customer_id": customer["customer_id"],
                            "customer_name": customer.get("customer_name"),
                            "memory_hit": customer["customer_id"] in memories_by_customer,
                            "last_compiled_at": (
                                memories_by_customer.get(customer["customer_id"], {}).get("last_compiled_at").isoformat()
                                if memories_by_customer.get(customer["customer_id"], {}).get("last_compiled_at")
                                else None
                            ),
                        }
                        for customer in customers[:5]
                    ],
                },
                {"memories_by_customer": memories_by_customer},
            )

        return run_node(state, "load_customer_memory", "customer_memory_loader", handler)

    def calculate_rule_risk_node(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            candidates: list[RiskCandidate] = []
            for customer in current_state.get("customers", []):
                deal = current_state.get("deals_by_customer", {}).get(customer["customer_id"])
                risk_result = calculate_risk_score(customer, deal)
                if risk_result["risk_score"] >= 40:
                    candidates.append({"customer": customer, "deal": deal, "risk_result": risk_result})
            return (
                {"candidate_count": len(candidates)},
                {"risk_candidates": candidates},
            )

        return run_node(state, "calculate_rule_risk", "risk_rule_tool", handler)

    def plan_risk_actions(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            planner_tools = [
                tool
                for tool in tool_gateway.list_tool_specs()
                if tool["name"] in {"crm.get_customer_detail", "report.query", "rag.retrieve_sales_context", "risk.generate_advice"}
            ]
            planned_actions = []
            total_steps = 0
            for candidate in current_state.get("risk_candidates", []):
                customer_memory = current_state.get("memories_by_customer", {}).get(candidate["customer"]["customer_id"])
                plan = plan_risk_tool_calls(
                    candidate["customer"],
                    candidate["deal"],
                    candidate["risk_result"],
                    planner_tools,
                    customer_memory=customer_memory,
                )
                planned_actions.append({**candidate, "plan": plan.model_dump(), "customer_memory": customer_memory})
                total_steps += len(plan.steps)
            return (
                {
                    "plan_count": len(planned_actions),
                    "total_steps": total_steps,
                    "plan_preview": [
                        {
                            "customer_id": item["customer"]["customer_id"],
                            "customer_name": item["customer"].get("customer_name"),
                            "thinking": item["plan"]["thinking"],
                            "tools": [step["tool_name"] for step in item["plan"]["steps"]],
                            "memory_hit": bool(item.get("customer_memory")),
                        }
                        for item in planned_actions[:5]
                    ],
                },
                {"planned_actions": planned_actions},
            )

        return run_node(state, "plan_risk_actions", "agent_planner", handler)

    def execute_risk_tools(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            context = ToolExecutionContext(
                tenant_id=current_state["tenant_id"],
                user_id=current_state["user_id"],
                run_id=current_state["run_id"],
                db=db,
            )
            executed_actions = []
            total_calls = 0
            for item in current_state.get("planned_actions", []):
                payload = {
                    "customer": item["customer"],
                    "deal": item["deal"],
                    "risk_result": item["risk_result"],
                    "customer_memory": item.get("customer_memory"),
                    "customer_id": item["customer"]["customer_id"],
                    "owner_user_id": item["customer"].get("owner_user_id"),
                }
                execution_records = []
                for step in item["plan"]["steps"]:
                    execution = tool_gateway.execute(step["tool_name"], context, payload)
                    execution_records.append(
                        {
                            "protocol": execution["protocol"],
                            "server_name": execution["server_name"],
                            "tool_name": execution["tool_name"],
                            "reason": step["reason"],
                            "audit_record": execution["audit_record"],
                            "output": execution["output"],
                        }
                    )
                    total_calls += 1
                    if step["tool_name"] == "crm.get_customer_detail":
                        payload["customer_detail"] = execution["output"]
                    elif step["tool_name"] == "report.query":
                        payload["related_reports"] = execution["output"].get("items", [])
                    elif step["tool_name"] == "rag.retrieve_sales_context":
                        payload["rag_result"] = execution["output"]
                    elif step["tool_name"] == "risk.generate_advice":
                        payload["advice"] = execution["output"]["advice"]
                        payload["context_summary"] = execution["output"].get("context_summary", "")
                executed_actions.append({**item, **payload, "tool_executions": execution_records})

            trace_ids = []
            for item in executed_actions:
                rag_result = item.get("rag_result", {})
                if rag_result.get("trace_id"):
                    trace_ids.append(rag_result["trace_id"])
            return (
                {
                    "execution_count": len(executed_actions),
                    "tool_call_count": total_calls,
                    "trace_ids": trace_ids,
                    "execution_preview": [
                        {
                            "customer_id": item["customer"]["customer_id"],
                            "customer_name": item["customer"].get("customer_name"),
                            "tools": [record["tool_name"] for record in item["tool_executions"]],
                            "context_tools": [
                                record["tool_name"]
                                for record in item["tool_executions"]
                                if record["tool_name"] in {"crm.get_customer_detail", "report.query"}
                            ],
                            "rag_trace_id": item.get("rag_result", {}).get("trace_id"),
                            "report_count": len(item.get("related_reports", [])),
                            "detail_loaded": bool(item.get("customer_detail")),
                            "memory_hit": bool(item.get("customer_memory")),
                            "advice_ready": bool(item.get("advice")),
                        }
                        for item in executed_actions[:5]
                    ],
                },
                {"executed_actions": executed_actions},
            )

        return run_node(state, "execute_risk_tools", "tool_executor", handler)

    def review_risk_actions(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            reviewed_actions = []
            approved_count = 0
            for item in current_state.get("executed_actions", []):
                review = review_risk_tool_results(
                    item["customer"],
                    item["deal"],
                    item["risk_result"],
                    item.get(
                        "rag_result",
                        {
                            "status": "skipped",
                            "trace_id": None,
                            "hit_count": 0,
                        },
                    ),
                    item.get("advice"),
                    customer_detail=item.get("customer_detail"),
                    related_reports=item.get("related_reports"),
                    tool_executions=item.get("tool_executions"),
                    customer_memory=item.get("customer_memory"),
                )
                reviewed_actions.append({**item, "review": review.model_dump()})
                if review.approved:
                    approved_count += 1
            return (
                {
                    "review_count": len(reviewed_actions),
                    "approved_count": approved_count,
                    "rejected_count": len(reviewed_actions) - approved_count,
                    "review_preview": [
                        {
                            "customer_id": item["customer"]["customer_id"],
                            "customer_name": item["customer"].get("customer_name"),
                            "approved": item["review"]["approved"],
                            "review_note": item["review"]["review_note"],
                            "evidence_used": item["review"].get("evidence_used", []),
                            "memory_hit": bool(item.get("customer_memory")),
                        }
                        for item in reviewed_actions[:5]
                    ],
                },
                {"reviewed_actions": reviewed_actions},
            )

        return run_node(state, "review_risk_actions", "agent_reviewer", handler)

    def create_approval_drafts(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            context = ToolExecutionContext(
                tenant_id=current_state["tenant_id"],
                user_id=current_state["user_id"],
                run_id=current_state["run_id"],
                db=db,
            )
            created = []
            skipped_reviews = []
            for item in current_state.get("reviewed_actions", []):
                review = item["review"]
                if not review["approved"]:
                    skipped_reviews.append(
                        {
                            "customer_id": item["customer"]["customer_id"],
                            "review_note": review["review_note"],
                        }
                    )
                    continue
                created_record = tool_gateway.execute(
                    "approval.create_risk_draft",
                    context,
                    {
                        "customer": item["customer"],
                        "deal": item["deal"],
                        "risk_result": item["risk_result"],
                        "rag_result": item.get(
                            "rag_result",
                            {
                                "status": "skipped",
                                "trace_id": None,
                                "hit_count": 0,
                                "context": "",
                                "sources": [],
                            },
                        ),
                        "advice": item.get("advice"),
                        "review": review,
                        "related_reports": item.get("related_reports", []),
                        "tool_executions": item.get("tool_executions", []),
                        "context_summary": item.get("context_summary", ""),
                    },
                )
                created.append(created_record["output"])
            return (
                {
                    "created_count": len(created),
                    "skipped_count": len(skipped_reviews),
                    "created_preview": created[:5],
                    "skipped_preview": skipped_reviews[:5],
                },
                {"created": created},
            )

        return run_node(state, "create_approval_drafts", "approval.create_risk_draft", handler)

    def persist_customer_memory(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            created_by_customer = {
                item["customer_id"]: item
                for item in current_state.get("created", [])
                if isinstance(item, dict) and item.get("customer_id")
            }
            updated_items: list[dict[str, Any]] = []
            for item in current_state.get("reviewed_actions", []):
                snapshot = build_customer_memory_snapshot(
                    db,
                    tenant_id=current_state["tenant_id"],
                    customer_id=item["customer"]["customer_id"],
                    source_run_id=current_state["run_id"],
                    runtime_context={
                        "review": item.get("review", {}),
                        "advice": item.get("advice", {}),
                        "tool_executions": item.get("tool_executions", []),
                        "created": created_by_customer.get(item["customer"]["customer_id"], {}),
                    },
                )
                if not snapshot:
                    continue
                updated_items.append(
                    upsert_customer_memory(
                        db,
                        tenant_id=current_state["tenant_id"],
                        memory_snapshot=snapshot,
                    )
                )
            return (
                {
                    "memory_updated_count": len(updated_items),
                    "memory_preview": [
                        {
                            "customer_id": item["customer_id"],
                            "memory_id": item["memory_id"],
                            "summary_text": item["summary_text"][:120],
                            "last_compiled_at": item["last_compiled_at"],
                        }
                        for item in updated_items[:5]
                    ],
                },
                {"memory_updates": updated_items},
            )

        return run_node(state, "persist_customer_memory", "customer_memory_writer", handler)

    def persist_agent_trace(state: RiskAnalysisState) -> dict[str, Any]:
        def handler(current_state: RiskAnalysisState):
            created = current_state.get("created", [])
            memory_updates = current_state.get("memory_updates", [])
            memory_hits = sum(
                1
                for item in current_state.get("planned_actions", [])
                if isinstance(item, dict) and item.get("customer_memory")
            )
            status = "awaiting_approval" if created else "success"
            output = {
                "risk_count": len(created),
                "approval_count": len(created),
                "items": created,
                "memory_summary": {
                    "memory_hit_count": memory_hits,
                    "memory_updated_count": len(memory_updates),
                    "memory_customer_count": len(current_state.get("customers", [])),
                },
            }
            db.execute(
                text(
                    """
                    UPDATE agent_run
                    SET output_json = :output_json,
                        status = :status,
                        finished_at = :finished_at,
                        total_duration_ms = :total_duration_ms
                    WHERE tenant_id = :tenant_id AND run_id = :run_id
                    """
                ),
                {
                    "tenant_id": current_state["tenant_id"],
                    "run_id": current_state["run_id"],
                    "output_json": _dumps(output),
                    "status": status,
                    "finished_at": datetime.now(),
                    "total_duration_ms": int((time.time() - current_state["started_ts"]) * 1000),
                },
            )
            return (
                {
                    "status": status,
                    "risk_count": len(created),
                    "approval_count": len(created),
                    "memory_hit_count": memory_hits,
                    "memory_updated_count": len(memory_updates),
                },
                {"status": status, "output": output},
            )

        return run_node(state, "persist_agent_trace", "agent_trace_tool", handler)

    graph = StateGraph(RiskAnalysisState)
    graph.add_node("load_crm_data", load_crm_data)
    graph.add_node("load_customer_memory", load_customer_memory)
    graph.add_node("calculate_rule_risk", calculate_rule_risk_node)
    graph.add_node("plan_risk_actions", plan_risk_actions)
    graph.add_node("execute_risk_tools", execute_risk_tools)
    graph.add_node("review_risk_actions", review_risk_actions)
    graph.add_node("create_approval_drafts", create_approval_drafts)
    graph.add_node("persist_customer_memory", persist_customer_memory)
    graph.add_node("persist_agent_trace", persist_agent_trace)

    graph.add_edge(START, "load_crm_data")
    graph.add_edge("load_crm_data", "load_customer_memory")
    graph.add_edge("load_customer_memory", "calculate_rule_risk")
    graph.add_edge("calculate_rule_risk", "plan_risk_actions")
    graph.add_edge("plan_risk_actions", "execute_risk_tools")
    graph.add_edge("execute_risk_tools", "review_risk_actions")
    graph.add_edge("review_risk_actions", "create_approval_drafts")
    graph.add_edge("create_approval_drafts", "persist_customer_memory")
    graph.add_edge("persist_customer_memory", "persist_agent_trace")
    graph.add_edge("persist_agent_trace", END)
    return graph.compile()


def run_risk_analysis_workflow(tenant_id: str, user_id: str, customer_id: str | None = None) -> dict[str, Any]:
    """执行风险扫描图，并保持现有返回结构与落库行为兼容。"""
    db = SessionLocal()
    run_id = new_id("run")
    started_at = datetime.now()
    started_ts = time.time()
    try:
        logger.info(
            "开始风险扫描: tenant_id=%s, user_id=%s, customer_id=%s, run_id=%s",
            tenant_id,
            user_id,
            customer_id,
            run_id,
        )
        db.execute(
            text(
                """
                INSERT INTO agent_run (
                  tenant_id, run_id, user_id, run_type, graph_name, input_json, status, started_at
                )
                VALUES (
                  :tenant_id, :run_id, :user_id, 'risk_analysis', 'risk_analysis_graph',
                  :input_json, 'running', :started_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "user_id": user_id,
                "input_json": _dumps(
                    {
                        "scope": "customer" if customer_id else "tenant",
                        "customer_id": customer_id,
                    }
                ),
                "started_at": started_at,
            },
        )
        # 中文注释：先把 run 头记录落盘，后续即使图执行失败，也能回写 failed 状态。
        db.commit()

        graph = build_risk_analysis_graph(db)
        final_state = graph.invoke(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "customer_id": customer_id,
                "run_id": run_id,
                "started_at": started_at,
                "started_ts": started_ts,
            }
        )
        db.commit()
        return {"run_id": run_id, "status": final_state["status"], **final_state["output"]}
    except Exception as exc:
        db.rollback()
        logger.exception("风险扫描失败: run_id=%s", run_id)
        try:
            _update_failed_run(db, tenant_id, run_id, exc, started_ts)
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
