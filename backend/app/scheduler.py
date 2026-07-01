from apscheduler.schedulers.background import BackgroundScheduler


def create_scheduler() -> BackgroundScheduler:
    """创建轻量定时调度器；V1 用于每天风险扫描和经营日报。"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return scheduler
