from threading import Event

from app.scheduler import create_scheduler


if __name__ == "__main__":
    # 中文注释：定时器独立进程启动，避免 FastAPI reload 或多 worker 场景重复注册任务。
    scheduler = create_scheduler(register_jobs=True)
    scheduler.start()
    print("InsightPilot scheduler started: daily_risk_scan=09:00, daily_business_report=18:00")
    Event().wait()
