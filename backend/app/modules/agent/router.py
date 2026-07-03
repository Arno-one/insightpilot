import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.agent import conversation_memory_service, memory_service
from app.modules.agent.schemas import RiskChatMessageRequest
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
    """查询单次 Agent Run 的完整审计链路：Run、Step、RAG Trace 和命中片段。"""
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

    steps = []
    trace_ids: list[str] = []
    for row in step_rows:
        step = dict(row)
        step["required_permissions_json"] = _loads_json(step.get("required_permissions_json"))
        step["input_json"] = _loads_json(step.get("input_json"))
        step["output_json"] = _loads_json(step.get("output_json"))
        trace_ids.extend(_collect_trace_ids_from_step(step))
        steps.append(step)

    rag_traces = []
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

    return success(
        {
            "run": run_data,
            "steps": steps,
            "rag_traces": rag_traces,
        },
        "查询成功",
        total=len(steps),
    )


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
    """发送一条 Risk Agent 对话消息，并把短期记忆压缩为最近 5 轮全量 + 历史摘要。"""
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
                    "content": body.message,
                    "created_at": "pending",
                },
            ],
        },
        user_message=body.message,
    )
    saved_memory, compacted = conversation_memory_service.append_conversation_messages(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
        messages=[
            {"role": "user", "content": body.message},
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

    return success(
        {
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
        },
        "回复成功",
    )


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
