from app.modules.agent.graphs.risk_analysis_graph import run_risk_analysis_workflow


def run_risk_scan(tenant_id: str, user_id: str, customer_id: str | None = None) -> dict:
    """RQ Worker 入口：支持租户级全量扫描，也支持客户详情页触发的单客户重算。"""
    return run_risk_analysis_workflow(tenant_id, user_id, customer_id=customer_id)
