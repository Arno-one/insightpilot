from app.modules.agent.graphs.business_report_graph import run_business_report_workflow


def generate_daily_report(tenant_id: str, user_id: str) -> dict:
    """RQ Worker 入口：真实执行逻辑由 LangGraph 经营日报图承接。"""
    return run_business_report_workflow(tenant_id, user_id)
