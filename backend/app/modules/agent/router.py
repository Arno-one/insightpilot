import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.database import get_db, get_readonly_db
from app.modules.agent import chat_session_service, conversation_memory_service, intent_router, memory_service, nl2sql_tool
from app.modules.agent.schemas import (
    AgentChatIntentRouteRequest,
    AgentChatMessageCreateRequest,
    AgentChatSessionCreateRequest,
    RiskChatMessageRequest,
)
from app.modules.auth.dependencies import require_permission
from app.modules.crm import service as crm_service
from app.modules.llm.client import generate_risk_chat_reply
from app.shared.response import success

router = APIRouter()


def _loads_json(value):
    """兼容 MySQL JSON 字段返回字符串或原生 dict/list 的情况。"""
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return value


def _collect_trace_ids_from_step(step: dict) -> list[str]:
    """从 Agent Step 输出中提取 RAG trace_id，便于详情页串起检索链路。"""
    trace_ids: list[str] = []
    output = step.get("output_json")
    if isinstance(output, dict):
        if output.get("trace_id"):
            trace_ids.append(output["trace_id"])
        for trace_id in output.get("trace_ids", []):
            if trace_id:
                trace_ids.append(trace_id)
    return trace_ids


def _load_action_run_bundles(db: Session, tenant_id: str, approval_ids: list[str]) -> list[dict]:
    if not approval_ids:
        return []
    run_rows = db.execute(
        text(
            """
            SELECT action_run_id, chain_code, approval_id, customer_id, trigger_source,
                   triggered_by_user_id, status, current_step_code, context_payload_json,
                   error_message, created_at, finished_at
            FROM agent_action_run
            WHERE tenant_id = :tenant_id
              AND approval_id IN :approval_ids
            ORDER BY created_at DESC
            """
        ).bindparams(bindparam("approval_ids", expanding=True)),
        {"tenant_id": tenant_id, "approval_ids": approval_ids},
    ).mappings().all()
    items: list[dict] = []
    for row in run_rows:
        run_item = dict(row)
        run_item["context_payload_json"] = _loads_json(run_item.get("context_payload_json"))
        step_rows = db.execute(
            text(
                """
                SELECT step_run_id, action_run_id, approval_id, customer_id, step_code, tool_name,
                       step_order, status, input_payload_json, output_payload_json, error_message,
                       retry_count, started_at, finished_at, created_at
                FROM agent_action_run_step
                WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id
                ORDER BY step_order ASC
                """
            ),
            {"tenant_id": tenant_id, "action_run_id": run_item["action_run_id"]},
        ).mappings().all()
        steps = []
        for step_row in step_rows:
            step = dict(step_row)
            step["input_payload_json"] = _loads_json(step.get("input_payload_json"))
            step["output_payload_json"] = _loads_json(step.get("output_payload_json"))
            steps.append(step)
        items.append(
            {
                **run_item,
                "task_id": (run_item.get("context_payload_json") or {}).get("task", {}).get("task_id"),
                "notification_id": (run_item.get("context_payload_json") or {}).get("notification", {}).get(
                    "notification_id"
                ),
                "can_retry": run_item.get("status") == "failed",
                "steps": steps,
            }
        )
    return items


def _collect_action_approval_ids(run_output: object) -> list[str]:
    """中文注释：优先从 Agent Run 输出里提取审批单，减少详情页回查数据库的次数。"""
    if not isinstance(run_output, dict):
        return []

    approval_ids: list[str] = []
    direct_approval_id = run_output.get("approval_id")
    if isinstance(direct_approval_id, str) and direct_approval_id:
        approval_ids.append(direct_approval_id)

    items = run_output.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            approval_id = item.get("approval_id")
            if isinstance(approval_id, str) and approval_id:
                approval_ids.append(approval_id)

    return list(dict.fromkeys(approval_ids))


def _load_latest_customer_risk_snapshot(db: Session, tenant_id: str, customer_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT risk_snapshot_id, risk_score, risk_level, llm_reason, llm_suggestion, status, created_at
            FROM customer_risk_snapshot
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().first()
    return dict(row) if row else {}


def _load_customer_memory_item(db: Session, tenant_id: str, customer_id: str) -> dict:
    return memory_service.load_customer_memory_map(db, tenant_id, [customer_id]).get(customer_id, {})


def _load_chat_session_or_404(db: Session, current_user: dict, session_id: str) -> dict:
    try:
        return chat_session_service.get_chat_session(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _build_risk_chat_session_payload(
    db: Session,
    current_user: dict,
    customer_id: str,
) -> dict:
    customer = crm_service.load_customer_or_404(db, current_user, customer_id)
    latest_risk = _load_latest_customer_risk_snapshot(db, current_user["tenant_id"], customer_id)
    customer_memory = _load_customer_memory_item(db, current_user["tenant_id"], customer_id)
    conversation_memory = conversation_memory_service.load_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )
    return {
        "session_key": conversation_memory["session_key"],
        "recent_messages": conversation_memory["recent_messages"],
        "history_summary": conversation_memory["history_summary"],
        "memory_window": conversation_memory["memory_window"],
        "updated_at": conversation_memory["updated_at"],
        "customer_brief": {
            "customer_id": customer["customer_id"],
            "customer_name": customer.get("customer_name"),
            "owner_user_id": customer.get("owner_user_id"),
            "owner_user_name": customer.get("owner_user_name"),
            "lifecycle_stage": customer.get("lifecycle_stage"),
            "intent_level": customer.get("intent_level"),
            "last_follow_up_at": customer.get("last_follow_up_at"),
            "next_follow_up_at": customer.get("next_follow_up_at"),
            "last_sentiment": customer.get("last_sentiment"),
        },
        "latest_risk": latest_risk,
        "customer_memory_summary": customer_memory.get("summary_text", ""),
        "customer_memory_updated_at": customer_memory.get("last_compiled_at"),
    }


def _run_risk_agent_chat_reply(db: Session, current_user: dict, customer_id: str, user_message: str) -> dict:
    """复用现有 Risk Agent 对话能力，给统一入口和旧 Risk Chat 保持同一套回复与记忆逻辑。"""
    customer = crm_service.load_customer_or_404(db, current_user, customer_id)
    latest_risk = _load_latest_customer_risk_snapshot(db, current_user["tenant_id"], customer_id)
    customer_memory = _load_customer_memory_item(db, current_user["tenant_id"], customer_id)
    conversation_memory = conversation_memory_service.load_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )

    reply = generate_risk_chat_reply(
        customer=customer,
        latest_risk=latest_risk,
        customer_memory=customer_memory,
        conversation_memory={
            "history_summary": conversation_memory.get("history_summary", ""),
            "recent_messages": [
                *list(conversation_memory.get("recent_messages", [])),
                {
                    "role": "user",
                    "content": user_message,
                    "created_at": "pending",
                },
            ],
        },
        user_message=user_message,
    )
    saved_memory, compacted = conversation_memory_service.append_conversation_messages(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ],
    )
    session_items = conversation_memory_service.upsert_conversation_session_index(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id=customer_id,
        customer_name=customer.get("customer_name") or customer_id,
        session_key=saved_memory["session_key"],
        recent_messages=saved_memory["recent_messages"],
        updated_at=saved_memory["updated_at"],
        latest_risk_level=latest_risk.get("risk_level"),
    )

    return {
        "reply": reply,
        "session_key": saved_memory["session_key"],
        "recent_messages": saved_memory["recent_messages"],
        "history_summary": saved_memory["history_summary"],
        "memory_window": saved_memory["memory_window"],
        "updated_at": saved_memory["updated_at"],
        "compacted": compacted,
        "customer_memory_summary": customer_memory.get("summary_text", ""),
        "latest_risk": latest_risk,
        "session_history": session_items,
    }


@router.get("/runs")
def list_agent_runs(
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT ar.run_id, ar.user_id, starter.real_name AS user_real_name, ar.run_type, ar.graph_name,
                   ar.status, ar.total_duration_ms, ar.started_at, ar.finished_at
            FROM agent_run ar
            LEFT JOIN sys_user starter
              ON starter.tenant_id = ar.tenant_id
             AND starter.user_id = ar.user_id
            WHERE ar.tenant_id = :tenant_id
            ORDER BY ar.started_at DESC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.get("/runs/{run_id}")
def get_agent_run_detail(
    run_id: str,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    """查询单次 Agent Run 的完整审计链路，包括节点、RAG 检索和动作链恢复信息。"""
    run = db.execute(
        text(
            """
            SELECT ar.run_id, ar.user_id, starter.real_name AS user_real_name, ar.run_type, ar.graph_name,
                   ar.input_json, ar.output_json, ar.status, ar.error_message, ar.started_at, ar.finished_at,
                   ar.total_duration_ms, ar.created_at
            FROM agent_run ar
            LEFT JOIN sys_user starter
              ON starter.tenant_id = ar.tenant_id
             AND starter.user_id = ar.user_id
            WHERE ar.tenant_id = :tenant_id AND ar.run_id = :run_id
            LIMIT 1
            """
        ),
        {"tenant_id": current_user["tenant_id"], "run_id": run_id},
    ).mappings().first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent Run 不存在")

    run_data = dict(run)
    run_data["input_json"] = _loads_json(run_data.get("input_json"))
    run_data["output_json"] = _loads_json(run_data.get("output_json"))

    step_rows = db.execute(
        text(
            """
            SELECT step_id, run_id, node_name, tool_name, required_permissions_json,
                   input_json, output_json, status, error_message, started_at, finished_at,
                   duration_ms, created_at
            FROM agent_step
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            ORDER BY started_at ASC, id ASC
            """
        ),
        {"tenant_id": current_user["tenant_id"], "run_id": run_id},
    ).mappings().all()

    steps: list[dict] = []
    trace_ids: list[str] = []
    for row in step_rows:
        step = dict(row)
        step["required_permissions_json"] = _loads_json(step.get("required_permissions_json"))
        step["input_json"] = _loads_json(step.get("input_json"))
        step["output_json"] = _loads_json(step.get("output_json"))
        trace_ids.extend(_collect_trace_ids_from_step(step))
        steps.append(step)

    rag_traces: list[dict] = []
    for trace_id in dict.fromkeys(trace_ids):
        trace_row = db.execute(
            text(
                """
                SELECT trace_id, user_id, original_query, rewritten_query, strategy,
                       rewrite_ms, embed_ms, search_ms, rerank_ms, total_ms, top_k,
                       hit_count, created_at
                FROM rag_retrieval_trace
                WHERE tenant_id = :tenant_id AND trace_id = :trace_id
                LIMIT 1
                """
            ),
            {"tenant_id": current_user["tenant_id"], "trace_id": trace_id},
        ).mappings().first()
        if not trace_row:
            continue
        hit_rows = db.execute(
            text(
                """
                SELECT hit_id, source_collection, source_type, doc_id, section_id,
                       rank_no, dense_score, sparse_score, rrf_score, rerank_score,
                       text_preview, created_at
                FROM rag_retrieval_hit
                WHERE tenant_id = :tenant_id AND trace_id = :trace_id
                ORDER BY rank_no ASC
                """
            ),
            {"tenant_id": current_user["tenant_id"], "trace_id": trace_id},
        ).mappings().all()
        rag_traces.append({**dict(trace_row), "hits": [dict(hit) for hit in hit_rows]})

    approval_ids = _collect_action_approval_ids(run_data.get("output_json"))
    if not approval_ids:
        approval_ids = db.execute(
            text(
                """
                SELECT approval_id
                FROM approval_record
                WHERE tenant_id = :tenant_id AND run_id = :run_id
                ORDER BY created_at DESC
                """
            ),
            {"tenant_id": current_user["tenant_id"], "run_id": run_id},
        ).scalars().all()

    action_runs = _load_action_run_bundles(
        db,
        current_user["tenant_id"],
        [approval_id for approval_id in dict.fromkeys(approval_ids) if approval_id],
    )

    return success(
        {
            "run": run_data,
            "steps": steps,
            "rag_traces": rag_traces,
            "action_runs": action_runs,
        },
        "查询成功",
        total=len(steps),
    )


@router.post("/chat/sessions")
def create_agent_chat_session(
    body: AgentChatSessionCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """创建统一 Agent 对话会话；V1 先做入口和持久化，不触发具体 Agent Runtime。"""
    if body.related_customer_id:
        # 中文注释：如果会话挂客户，必须先复用 CRM 权限校验，避免越权创建客户上下文会话。
        crm_service.load_customer_or_404(db, current_user, body.related_customer_id)

    data = chat_session_service.create_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        agent_scope=body.agent_scope,
        intent=body.intent,
        title=body.title,
        related_customer_id=body.related_customer_id,
        context_json=body.context_json,
    )
    return success(data, "统一 Agent 对话会话已创建")


@router.get("/chat/sessions")
def list_agent_chat_sessions(
    agent_scope: str | None = None,
    status: str = "active",
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询当前用户的统一 Agent 对话会话列表。"""
    data = chat_session_service.list_chat_sessions(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        agent_scope=agent_scope,
        status=status,
        limit=limit,
    )
    return success(data, "查询成功", total=len(data))


@router.get("/chat/sessions/{session_id}")
def get_agent_chat_session_detail(
    session_id: str,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询统一 Agent 对话会话详情和消息明细。"""
    session = _load_chat_session_or_404(db, current_user, session_id)
    messages = chat_session_service.list_chat_messages(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        limit=limit,
    )
    return success({"session": session, "messages": messages}, "查询成功", total=len(messages))


@router.post("/chat/intent")
def route_agent_chat_intent(
    body: AgentChatIntentRouteRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """识别统一 Agent 对话意图；V1 只返回路由结果，不执行具体工具。"""
    _ = current_user
    result = intent_router.route_intent(body.question)
    return success(result.model_dump(), "意图识别完成")


@router.post("/chat/sessions/{session_id}/messages")
def append_agent_chat_user_message(
    session_id: str,
    body: AgentChatMessageCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
    readonly_db: Session = Depends(get_readonly_db),
):
    """统一入口写入用户消息；Agent 回复会在后续 Runtime 接入时由服务层写入。"""
    if body.role != "user":
        raise HTTPException(status_code=400, detail="统一对话入口 V1 仅允许直接写入用户消息")

    current_session = _load_chat_session_or_404(db, current_user, session_id)
    route_result = intent_router.route_intent(body.content)
    resolved_intent = body.intent or route_result.intent
    message = chat_session_service.append_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="user",
        content=body.content,
        intent=resolved_intent,
        tool_name=body.tool_name,
        run_id=body.run_id,
        trace_id=body.trace_id,
        metadata_json={
            **(body.metadata_json or {}),
            "intent_route": route_result.model_dump(),
        },
    )
    assistant_message = None
    runtime_result = {
        "handled": False,
        "handler": None,
        "reason": "当前意图暂未接入统一运行时",
    }

    if resolved_intent == intent_router.INTENT_DATA_QUERY:
        nl2sql_result = nl2sql_tool.run_nl2sql_tool(
            db,
            readonly_db,
            current_user,
            question=body.content,
        )
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=nl2sql_result["reply"],
            intent=resolved_intent,
            tool_name="data.query_sql",
            metadata_json={
                "runtime_handler": "data.query_sql",
                "query_id": nl2sql_result["query_id"],
                "nl2sql_session_id": nl2sql_result["nl2sql_session_id"],
                "is_cached": nl2sql_result["is_cached"],
                "row_count": nl2sql_result["row_count"],
                "error": nl2sql_result["error"],
                "sql": nl2sql_result["nl2sql"].get("sql"),
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "data.query_sql",
            "reply": nl2sql_result["reply"],
            "nl2sql": nl2sql_result["nl2sql"],
        }
    elif resolved_intent == intent_router.INTENT_RISK_ANALYSIS and current_session.get("related_customer_id"):
        risk_result = _run_risk_agent_chat_reply(
            db,
            current_user,
            current_session["related_customer_id"],
            body.content,
        )
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=risk_result["reply"],
            intent=resolved_intent,
            metadata_json={
                "runtime_handler": "risk_agent",
                "risk_chat": {
                    "session_key": risk_result["session_key"],
                    "compacted": risk_result["compacted"],
                    "latest_risk": risk_result["latest_risk"],
                },
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "risk_agent",
            "reply": risk_result["reply"],
            "risk_chat": risk_result,
        }
    elif resolved_intent == intent_router.INTENT_RISK_ANALYSIS:
        runtime_result = {
            "handled": False,
            "handler": "risk_agent",
            "reason": "风险分析需要会话先关联客户",
        }

    session = chat_session_service.get_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
    )
    return success(
        {
            "session": session,
            "message": message,
            "assistant_message": assistant_message,
            "intent_route": route_result.model_dump(),
            "runtime": runtime_result,
        },
        "消息已写入统一 Agent 对话",
    )


@router.post("/chat/sessions/{session_id}/close")
def close_agent_chat_session(
    session_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """关闭统一 Agent 对话会话，保留消息审计记录。"""
    _load_chat_session_or_404(db, current_user, session_id)
    data = chat_session_service.close_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
    )
    return success(data, "统一 Agent 对话会话已关闭")


@router.get("/risk-chat/customers/{customer_id}/session")
def get_risk_chat_session(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """读取当前用户在当前客户下的 Risk Agent 对话会话和记忆窗口。"""
    data = _build_risk_chat_session_payload(db, current_user, customer_id)
    return success(data, "查询成功")


@router.get("/risk-chat/sessions")
def list_risk_chat_sessions(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """返回当前用户的对话历史索引，供客户工作台左侧会话列表直接展示。"""
    data = conversation_memory_service.list_conversation_sessions(
        current_user["tenant_id"],
        current_user["user_id"],
    )
    return success(data, "查询成功", total=len(data))


@router.post("/risk-chat/customers/{customer_id}/message")
def send_risk_chat_message(
    customer_id: str,
    body: RiskChatMessageRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """发送一条 Risk Agent 对话消息，并把短期记忆压缩为最近 5 轮全量加历史摘要。"""
    return success(_run_risk_agent_chat_reply(db, current_user, customer_id, body.message), "回复成功")


@router.delete("/risk-chat/customers/{customer_id}/session")
def clear_risk_chat_session(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """清空当前用户在该客户下的 Risk Agent 短期会话记忆。"""
    crm_service.load_customer_or_404(db, current_user, customer_id)
    conversation_memory_service.clear_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )
    session_items = conversation_memory_service.remove_conversation_session_index(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id=customer_id,
    )
    return success({"customer_id": customer_id, "session_history": session_items}, "会话记忆已清空")
