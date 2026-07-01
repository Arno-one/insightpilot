import json
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.llm.client import generate_risk_advice
from app.modules.risk.rules import calculate_risk_score
from app.shared.ids import new_id

logger = logging.getLogger(__name__)


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dumps(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _insert_step(db, tenant_id: str, run_id: str, node_name: str, status: str, started: float, output: dict, tool_name: str | None = None):
    """记录 Agent 节点执行情况，方便前端展示 LangGraph Trace。"""
    finished = time.time()
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, started_at, finished_at, duration_ms
            )
            VALUES (
              :tenant_id, :step_id, :run_id, :node_name, :tool_name, :input_json, :output_json,
              :status, :started_at, :finished_at, :duration_ms
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
            "started_at": datetime.fromtimestamp(started),
            "finished_at": datetime.fromtimestamp(finished),
            "duration_ms": int((finished - started) * 1000),
        },
    )


def _load_customers(db, tenant_id: str) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT *
            FROM crm_customer
            WHERE tenant_id = :tenant_id
              AND lifecycle_stage NOT IN ('won', 'lost')
            ORDER BY updated_at DESC
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def _load_deals_by_customer(db, tenant_id: str) -> dict[str, dict]:
    rows = db.execute(
        text(
            """
            SELECT *
            FROM crm_deal
            WHERE tenant_id = :tenant_id
              AND close_result = 'open'
            ORDER BY updated_at DESC
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    deals: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        deals.setdefault(item["customer_id"], item)
    return deals


def _approval_due_policy(risk_level: str) -> str:
    return "tomorrow" if risk_level == "high" else "in_2_days"


def _insert_risk_and_approval(db, tenant_id: str, run_id: str, requester_user_id: str, customer: dict, deal: dict | None, risk_result: dict) -> dict:
    advice = generate_risk_advice(customer, deal, risk_result)
    risk_snapshot_id = new_id("risk")
    approval_id = new_id("appr")

    suggested_task = {
        "task_type": advice.task_type,
        "title": advice.task_title,
        "assignee_user_id": customer["owner_user_id"],
        "priority": advice.priority,
        "due_at": _approval_due_policy(risk_result["risk_level"]),
        "recommended_script": advice.recommended_script,
        "description": advice.suggestion,
    }

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
            "risk_score": risk_result["risk_score"],
            "risk_level": risk_result["risk_level"],
            "rule_hits_json": _dumps(risk_result["rule_hits"]),
            "evidence_json": _dumps(risk_result["evidence"]),
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

    return {
        "risk_snapshot_id": risk_snapshot_id,
        "approval_id": approval_id,
        "customer_id": customer["customer_id"],
        "risk_score": risk_result["risk_score"],
        "risk_level": risk_result["risk_level"],
    }


def run_risk_scan(tenant_id: str, user_id: str) -> dict:
    """执行客户风险扫描：规则打分 → LLM 解释 → 风险快照 → 待审批任务草稿。"""
    db = SessionLocal()
    run_id = new_id("run")
    started_at = datetime.now()
    started_ts = time.time()
    try:
        logger.info("开始风险扫描: tenant_id=%s, user_id=%s, run_id=%s", tenant_id, user_id, run_id)
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
                "input_json": _dumps({"scope": "tenant"}),
                "started_at": started_at,
            },
        )

        t0 = time.time()
        customers = _load_customers(db, tenant_id)
        deals = _load_deals_by_customer(db, tenant_id)
        _insert_step(db, tenant_id, run_id, "load_crm_data", "success", t0, {"customer_count": len(customers), "deal_count": len(deals)}, "crm_query_tool")

        t0 = time.time()
        risk_candidates = []
        for customer in customers:
            deal = deals.get(customer["customer_id"])
            risk_result = calculate_risk_score(customer, deal)
            if risk_result["risk_score"] >= 40:
                risk_candidates.append((customer, deal, risk_result))
        _insert_step(db, tenant_id, run_id, "calculate_rule_risk", "success", t0, {"candidate_count": len(risk_candidates)}, "risk_rule_tool")

        t0 = time.time()
        created = []
        for customer, deal, risk_result in risk_candidates:
            created.append(_insert_risk_and_approval(db, tenant_id, run_id, user_id, customer, deal, risk_result))
        _insert_step(db, tenant_id, run_id, "generate_task_draft", "success", t0, {"created_count": len(created)}, "llm_risk_advice_tool")

        finished_at = datetime.now()
        status = "awaiting_approval" if created else "success"
        output = {
            "risk_count": len(created),
            "approval_count": len(created),
            "items": created,
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
                "tenant_id": tenant_id,
                "run_id": run_id,
                "output_json": _dumps(output),
                "status": status,
                "finished_at": finished_at,
                "total_duration_ms": int((time.time() - started_ts) * 1000),
            },
        )
        db.commit()
        return {"run_id": run_id, "status": status, **output}
    except Exception as exc:
        db.rollback()
        logger.exception("风险扫描失败: run_id=%s", run_id)
        try:
            db.execute(
                text(
                    """
                    UPDATE agent_run
                    SET status = 'failed', error_message = :error_message, finished_at = :finished_at
                    WHERE tenant_id = :tenant_id AND run_id = :run_id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                    "error_message": str(exc),
                    "finished_at": datetime.now(),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
