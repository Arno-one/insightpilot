import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
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


@router.get("/runs")
def list_agent_runs(
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT run_id, user_id, run_type, graph_name, status, total_duration_ms, started_at, finished_at
            FROM agent_run
            WHERE tenant_id = :tenant_id
            ORDER BY started_at DESC
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
            SELECT run_id, user_id, run_type, graph_name, input_json, output_json,
                   status, error_message, started_at, finished_at, total_duration_ms, created_at
            FROM agent_run
            WHERE tenant_id = :tenant_id AND run_id = :run_id
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
