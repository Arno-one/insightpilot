from __future__ import annotations

from typing import Any


def _compact_text(value: Any, *, max_length: int = 140) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        text = "；".join(str(item) for item in value[:3])
    elif isinstance(value, dict):
        text = "；".join(f"{key}:{item}" for key, item in list(value.items())[:3])
    else:
        text = str(value)
    return text if len(text) <= max_length else f"{text[: max_length - 3]}..."


def _top_risk_items(customer_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for detail in customer_details:
        customer = detail.get("customer") or {}
        risk_snapshots = detail.get("risk_snapshots") or []
        if not risk_snapshots:
            continue
        risk = risk_snapshots[0]
        items.append(
            {
                "customer_id": customer.get("customer_id"),
                "customer_name": customer.get("customer_name"),
                "owner_user_id": customer.get("owner_user_id"),
                "owner_user_name": customer.get("owner_user_name"),
                "risk_score": risk.get("risk_score") or 0,
                "risk_level": risk.get("risk_level"),
                "reason": _compact_text(risk.get("llm_reason") or risk.get("evidence_json")),
                "suggestion": _compact_text(risk.get("llm_suggestion") or risk.get("suggested_task_json")),
            }
        )
    return sorted(items, key=lambda item: item.get("risk_score") or 0, reverse=True)[:5]


def _build_conclusions(question: str, analysis: dict[str, Any], top_risks: list[dict[str, Any]]) -> list[str]:
    conclusions: list[str] = []
    summary = analysis.get("summary")
    if summary:
        conclusions.append(summary)
    if top_risks:
        first = top_risks[0]
        conclusions.append(
            f"当前优先关注 {first.get('customer_name') or first.get('customer_id')}，"
            f"风险分 {first.get('risk_score')}，等级 {first.get('risk_level') or '未知'}。"
        )
    if not conclusions:
        conclusions.append("当前数据不足以形成强决策，建议先补齐关键经营指标和客户风险数据。")
    if "优先" in question or "重点" in question:
        conclusions.append("建议按风险分、客户价值和未完成任务紧急度排序处理。")
    return conclusions


def _build_evidence(analysis: dict[str, Any], reports: dict[str, Any], top_risks: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    for item in list(analysis.get("trend_insights") or [])[:2]:
        evidence.append(f"趋势：{item}")
    for item in list(analysis.get("anomaly_insights") or [])[:2]:
        evidence.append(f"异常：{item}")
    for item in list(analysis.get("topn_attribution") or [])[:2]:
        evidence.append(f"归因：{item}")
    for item in list(analysis.get("report_references") or [])[:2]:
        evidence.append(f"报告：{item}")
    for item in top_risks[:3]:
        evidence.append(
            f"风险：{item.get('customer_name') or item.get('customer_id')} "
            f"{item.get('risk_level') or '未知'} / {item.get('risk_score')}"
        )
    if reports.get("skipped_reason"):
        evidence.append(f"报告联动跳过：{reports['skipped_reason']}")
    return evidence


def _build_recommended_actions(customer_details: list[dict[str, Any]], top_risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in top_risks[:3]:
        actions.append(
            {
                "action_type": "create_follow_up_task",
                "priority": "high" if (item.get("risk_score") or 0) >= 80 else "medium",
                "customer_id": item.get("customer_id"),
                "customer_name": item.get("customer_name"),
                "owner_user_id": item.get("owner_user_id"),
                "title": f"跟进高风险客户：{item.get('customer_name') or item.get('customer_id')}",
                "reason": item.get("reason") or "客户进入高风险队列，需要负责人复盘并补充跟进动作。",
                "requires_approval": True,
            }
        )

    open_task_count = 0
    pending_approval_count = 0
    for detail in customer_details:
        open_task_count += len([task for task in detail.get("tasks") or [] if task.get("status") in {"pending", "in_progress"}])
        pending_approval_count += len([item for item in detail.get("approvals") or [] if item.get("status") == "pending"])
    if open_task_count:
        actions.append(
            {
                "action_type": "review_open_tasks",
                "priority": "medium",
                "title": f"复核 {open_task_count} 个未完成任务",
                "reason": "存在未完成任务，建议先确认是否阻塞客户推进。",
                "requires_approval": False,
            }
        )
    if pending_approval_count:
        actions.append(
            {
                "action_type": "review_pending_approvals",
                "priority": "medium",
                "title": f"处理 {pending_approval_count} 个待审批动作",
                "reason": "待审批动作可能影响后续执行链路，需要人工确认。",
                "requires_approval": False,
            }
        )
    return actions[:5]


def build_manager_decision(
    question: str,
    *,
    data_analysis: dict[str, Any],
    customer_search: dict[str, Any],
    customer_details: list[dict[str, Any]],
    report_context: dict[str, Any],
) -> dict[str, Any]:
    """把经营分析、CRM、风险、审批和任务上下文整理成经理视角决策输出。"""
    analysis = data_analysis.get("analysis") or {}
    top_risks = _top_risk_items(customer_details)
    actions = _build_recommended_actions(customer_details, top_risks)
    return {
        "protocol": "manager.decision.v1",
        "question": question,
        "conclusions": _build_conclusions(question, analysis, top_risks),
        "evidence": _build_evidence(analysis, report_context, top_risks),
        "recommended_actions": actions,
        "execution_policy": {
            "auto_execute": False,
            "approval_required_action_types": [
                action["action_type"] for action in actions if action.get("requires_approval")
            ],
            "note": "VNext-6 只生成决策建议，不自动创建审批、任务或外发动作。",
        },
        "linked_capabilities": {
            "data_query": bool((data_analysis.get("query") or {}).get("query_id")),
            "report": int(report_context.get("total") or 0),
            "crm": int(customer_search.get("total") or 0),
            "risk": len(top_risks),
            "approval": sum(len(detail.get("approvals") or []) for detail in customer_details),
            "task": sum(len(detail.get("tasks") or []) for detail in customer_details),
        },
    }
