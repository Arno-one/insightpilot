import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.llm.client import generate_business_report_narrative
from app.shared.ids import new_id

logger = logging.getLogger(__name__)


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dumps(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _to_int(value) -> int:
    """把数据库 COUNT/SUM 计数结果转成整数，避免日报出现 10.0 这类展示噪音。"""
    if value is None:
        return 0
    return int(value)


def _to_float(value) -> float:
    """把金额类聚合结果转成浮点数，后续前端可再做货币格式化。"""
    if value is None:
        return 0.0
    return float(value)


def _insert_step(db, tenant_id: str, run_id: str, node_name: str, status: str, started: float, output: dict, tool_name: str | None = None):
    """记录经营日报 Agent 节点，前端可复用 Agent Trace 页面查看执行过程。"""
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


def _collect_metrics(db, tenant_id: str, report_date: date) -> dict:
    """汇总日报核心指标；V1 先用 SQL 聚合，后续可拆成指标服务。"""
    customer_stats = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS total_customers,
              SUM(CASE WHEN lifecycle_stage NOT IN ('won', 'lost') THEN 1 ELSE 0 END) AS active_customers,
              SUM(CASE WHEN lifecycle_stage = 'quotation' THEN 1 ELSE 0 END) AS quotation_customers,
              SUM(CASE WHEN competitor_involved = 1 THEN 1 ELSE 0 END) AS competitor_customers
            FROM crm_customer
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().one()

    deal_stats = db.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN close_result = 'open' THEN 1 ELSE 0 END) AS open_deals,
              COALESCE(SUM(CASE WHEN close_result = 'open' THEN amount ELSE 0 END), 0) AS open_deal_amount,
              SUM(CASE WHEN close_result = 'open' AND stage = 'quotation' THEN 1 ELSE 0 END) AS quotation_deals,
              SUM(CASE WHEN close_result = 'won' AND DATE(closed_at) = :report_date THEN 1 ELSE 0 END) AS won_today
            FROM crm_deal
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": tenant_id, "report_date": report_date},
    ).mappings().one()

    follow_up_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM crm_follow_up_record
            WHERE tenant_id = :tenant_id AND DATE(occurred_at) = :report_date
            """
        ),
        {"tenant_id": tenant_id, "report_date": report_date},
    ).scalar_one()

    risk_rows = db.execute(
        text(
            """
            SELECT r.risk_level, COUNT(*) AS risk_count
            FROM customer_risk_snapshot r
            JOIN (
              SELECT customer_id, MAX(id) AS max_id
              FROM customer_risk_snapshot
              WHERE tenant_id = :tenant_id
              GROUP BY customer_id
            ) latest ON latest.max_id = r.id
            WHERE r.tenant_id = :tenant_id
            GROUP BY r.risk_level
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    risk_map = {row["risk_level"]: row["risk_count"] for row in risk_rows}

    approval_stats = db.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_approvals,
              SUM(CASE WHEN status = 'approved' AND DATE(reviewed_at) = :report_date THEN 1 ELSE 0 END) AS approved_today
            FROM approval_record
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": tenant_id, "report_date": report_date},
    ).mappings().one()

    task_stats = db.execute(
        text(
            """
            SELECT
              SUM(CASE WHEN status IN ('pending', 'in_progress') THEN 1 ELSE 0 END) AS active_tasks,
              SUM(CASE WHEN status IN ('pending', 'in_progress') AND due_at < NOW() THEN 1 ELSE 0 END) AS overdue_tasks,
              SUM(CASE WHEN status IN ('pending', 'in_progress') AND DATE(due_at) = :report_date THEN 1 ELSE 0 END) AS due_today_tasks
            FROM sales_task
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": tenant_id, "report_date": report_date},
    ).mappings().one()

    return {
        "report_date": report_date.isoformat(),
        "total_customers": _to_int(customer_stats["total_customers"]),
        "active_customers": _to_int(customer_stats["active_customers"]),
        "quotation_customers": _to_int(customer_stats["quotation_customers"]),
        "competitor_customers": _to_int(customer_stats["competitor_customers"]),
        "open_deals": _to_int(deal_stats["open_deals"]),
        "open_deal_amount": _to_float(deal_stats["open_deal_amount"]),
        "quotation_deals": _to_int(deal_stats["quotation_deals"]),
        "won_today": _to_int(deal_stats["won_today"]),
        "effective_followups": _to_int(follow_up_count),
        "high_risk_customers": _to_int(risk_map.get("high", 0)),
        "medium_risk_customers": _to_int(risk_map.get("medium", 0)),
        "pending_approvals": _to_int(approval_stats["pending_approvals"]),
        "approved_today": _to_int(approval_stats["approved_today"]),
        "active_tasks": _to_int(task_stats["active_tasks"]),
        "overdue_tasks": _to_int(task_stats["overdue_tasks"]),
        "due_today_tasks": _to_int(task_stats["due_today_tasks"]),
    }


def _load_risk_top(db, tenant_id: str) -> list[dict]:
    """读取每个客户最新风险快照的 Top 列表，避免多次扫描造成同一客户重复上榜。"""
    rows = db.execute(
        text(
            """
            SELECT
              r.risk_snapshot_id,
              r.customer_id,
              c.customer_name,
              r.owner_user_id,
              r.risk_score,
              r.risk_level,
              r.llm_reason,
              r.llm_suggestion,
              r.created_at
            FROM customer_risk_snapshot r
            JOIN (
              SELECT customer_id, MAX(id) AS max_id
              FROM customer_risk_snapshot
              WHERE tenant_id = :tenant_id
              GROUP BY customer_id
            ) latest ON latest.max_id = r.id
            LEFT JOIN crm_customer c ON c.tenant_id = r.tenant_id AND c.customer_id = r.customer_id
            WHERE r.tenant_id = :tenant_id
              AND r.risk_level IN ('high', 'medium')
            ORDER BY r.risk_score DESC, r.created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def generate_daily_report(tenant_id: str, user_id: str) -> dict:
    """生成经营日报：指标汇总 -> 风险 Top -> 摘要建议 -> 报表落库。"""
    db = SessionLocal()
    run_id = new_id("run")
    report_id = new_id("report")
    report_date = date.today()
    started_at = datetime.now()
    started_ts = time.time()
    try:
        logger.info("开始生成经营日报: tenant_id=%s, user_id=%s, run_id=%s", tenant_id, user_id, run_id)
        db.execute(
            text(
                """
                INSERT INTO agent_run (
                  tenant_id, run_id, user_id, run_type, graph_name, input_json, status, started_at
                )
                VALUES (
                  :tenant_id, :run_id, :user_id, 'business_report', 'business_report_graph',
                  :input_json, 'running', :started_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "user_id": user_id,
                "input_json": _dumps({"report_type": "daily", "report_date": report_date}),
                "started_at": started_at,
            },
        )

        t0 = time.time()
        metrics = _collect_metrics(db, tenant_id, report_date)
        _insert_step(db, tenant_id, run_id, "collect_business_metrics", "success", t0, metrics, "business_metric_sql_tool")

        t0 = time.time()
        risk_top = _load_risk_top(db, tenant_id)
        _insert_step(db, tenant_id, run_id, "analyze_risk_top", "success", t0, {"risk_top_count": len(risk_top), "items": risk_top}, "risk_snapshot_sql_tool")

        t0 = time.time()
        narrative = generate_business_report_narrative(metrics, risk_top)
        _insert_step(
            db,
            tenant_id,
            run_id,
            "generate_report_narrative",
            "success",
            t0,
            {"summary": narrative.summary, "suggestions": narrative.suggestions},
            "llm_report_narrative_tool",
        )

        t0 = time.time()
        db.execute(
            text(
                """
                INSERT INTO business_report (
                  tenant_id, report_id, run_id, report_type, report_date,
                  summary, metrics_json, risk_top_json, suggestions, created_by_user_id
                )
                VALUES (
                  :tenant_id, :report_id, :run_id, 'daily', :report_date,
                  :summary, :metrics_json, :risk_top_json, :suggestions, :created_by_user_id
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "report_id": report_id,
                "run_id": run_id,
                "report_date": report_date,
                "summary": narrative.summary,
                "metrics_json": _dumps(metrics),
                "risk_top_json": _dumps(risk_top),
                "suggestions": narrative.suggestions,
                "created_by_user_id": user_id,
            },
        )
        _insert_step(db, tenant_id, run_id, "persist_business_report", "success", t0, {"report_id": report_id}, "business_report_repository")

        output = {
            "report_id": report_id,
            "report_type": "daily",
            "report_date": report_date.isoformat(),
            "metrics": metrics,
            "risk_top_count": len(risk_top),
        }
        db.execute(
            text(
                """
                UPDATE agent_run
                SET output_json = :output_json,
                    status = 'success',
                    finished_at = :finished_at,
                    total_duration_ms = :total_duration_ms
                WHERE tenant_id = :tenant_id AND run_id = :run_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "output_json": _dumps(output),
                "finished_at": datetime.now(),
                "total_duration_ms": int((time.time() - started_ts) * 1000),
            },
        )
        db.commit()
        return {"run_id": run_id, "status": "success", **output}
    except Exception as exc:
        db.rollback()
        logger.exception("经营日报生成失败: run_id=%s", run_id)
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
