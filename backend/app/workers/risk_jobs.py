from app.modules.agent.graphs.risk_analysis_graph import run_risk_analysis_workflow


def run_risk_scan(tenant_id: str, user_id: str) -> dict:
    """RQ Worker 入口：真实执行逻辑由 LangGraph 风险扫描图承接。"""
    return run_risk_analysis_workflow(tenant_id, user_id)
