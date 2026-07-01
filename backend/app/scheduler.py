from apscheduler.schedulers.background import BackgroundScheduler

from app.core.queue import get_default_queue

DEFAULT_TENANT_ID = "demo_tenant"
RISK_SCAN_USER_ID = "u_manager_001"
REPORT_USER_ID = "u_owner_001"


def enqueue_risk_scan(queue=None, tenant_id: str = DEFAULT_TENANT_ID, user_id: str = RISK_SCAN_USER_ID) -> str:
    """定时触发风险扫描；V1 固定 demo_tenant，后续完整多租户时改为按租户遍历。"""
    queue = queue or get_default_queue()
    job = queue.enqueue(
        "app.workers.risk_jobs.run_risk_scan",
        tenant_id,
        user_id,
        job_timeout=600,
    )
    return job.id


def enqueue_daily_report(queue=None, tenant_id: str = DEFAULT_TENANT_ID, user_id: str = REPORT_USER_ID) -> str:
    """定时触发经营日报；按钮触发仍是 V1 主路径，定时扫描作为轻量补充。"""
    queue = queue or get_default_queue()
    job = queue.enqueue(
        "app.workers.report_jobs.generate_daily_report",
        tenant_id,
        user_id,
        job_timeout=600,
    )
    return job.id


def register_default_jobs(scheduler: BackgroundScheduler) -> BackgroundScheduler:
    """注册 V1 默认定时任务，不立即启动，方便测试和启动脚本显式控制。"""
    scheduler.add_job(
        enqueue_risk_scan,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_risk_scan",
        name="每日客户风险扫描",
        replace_existing=True,
    )
    scheduler.add_job(
        enqueue_daily_report,
        trigger="cron",
        hour=18,
        minute=0,
        id="daily_business_report",
        name="每日经营日报生成",
        replace_existing=True,
    )
    return scheduler


def create_scheduler(register_jobs: bool = True) -> BackgroundScheduler:
    """创建轻量定时调度器；V1 用于每天风险扫描和经营日报。"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    if register_jobs:
        register_default_jobs(scheduler)
    return scheduler
