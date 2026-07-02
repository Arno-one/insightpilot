from app.modules.agent.graphs.business_report_graph import run_business_report_workflow


def generate_business_report(
    tenant_id: str,
    user_id: str,
    report_type: str = "daily",
    report_date: str | None = None,
) -> dict:
    """RQ Worker 入口：支持日报、周报和月报三类经营报告。"""
    return run_business_report_workflow(
        tenant_id=tenant_id,
        user_id=user_id,
        report_type=report_type,
        report_date=report_date,
    )


def generate_daily_report(tenant_id: str, user_id: str) -> dict:
    """兼容旧调用方，内部统一转到通用报告生成入口。"""
    return generate_business_report(tenant_id=tenant_id, user_id=user_id, report_type="daily")
