# RQ 与 APScheduler 联动测试记录

## 测试目标

验证 InsightPilot V1 的异步任务与轻量定时扫描能力：

- RQ 队列入口可承载风险扫描、RAG 入库和经营日报任务。
- APScheduler 能注册默认定时任务。
- 定时任务触发后会 enqueue 到正确的 Worker 函数。
- 定时器以独立进程启动，避免 FastAPI reload 或多 worker 场景重复触发。

## 本次代码入口

- RQ Worker：`backend/worker.py`
- APScheduler 启动入口：`backend/scheduler_worker.py`
- 调度注册：`backend/app/scheduler.py`

默认定时任务：

- `daily_risk_scan`：每天 09:00，入队 `app.workers.risk_jobs.run_risk_scan`
- `daily_business_report`：每天 18:00，入队 `app.workers.report_jobs.generate_daily_report`

## 执行命令

后端完整编译：

```powershell
python -m compileall backend -q
```

调度器注册与 enqueue 参数测试：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
from app.scheduler import create_scheduler, enqueue_daily_report, enqueue_risk_scan

class DummyJob:
    def __init__(self, job_id):
        self.id = job_id

class DummyQueue:
    def __init__(self):
        self.calls = []
    def enqueue(self, func_path, *args, **kwargs):
        self.calls.append({'func_path': func_path, 'args': args, 'kwargs': kwargs})
        return DummyJob(f'job_{len(self.calls)}')

scheduler = create_scheduler(register_jobs=True)
print(sorted(job.id for job in scheduler.get_jobs()))

queue = DummyQueue()
print(enqueue_risk_scan(queue=queue))
print(enqueue_daily_report(queue=queue))
print(queue.calls)
'@ | python
```

Redis/RQ 在线探测：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
from app.core.redis import get_redis
from app.scheduler import enqueue_daily_report

try:
    client = get_redis()
    print(client.ping())
    print(enqueue_daily_report())
except Exception as exc:
    print(type(exc).__name__, str(exc))
'@ | python
```

## 测试结果

编译结果：

- `python -m compileall backend -q` 通过。

调度器注册结果：

```text
JOB_IDS= ['daily_business_report', 'daily_risk_scan']
```

enqueue 参数结果：

```text
app.workers.risk_jobs.run_risk_scan
args=('demo_tenant', 'u_manager_001')
job_timeout=600

app.workers.report_jobs.generate_daily_report
args=('demo_tenant', 'u_owner_001')
job_timeout=600
```

依赖补齐：

- 本机 Python 环境缺少 `APScheduler`，已执行 `python -m pip install APScheduler`。
- 本机 Python 环境缺少 `redis` 和 `rq`，已执行 `python -m pip install redis rq`。
- 这些依赖原本已经在 `backend/requirements.txt` 中声明，本次只是补齐当前解释器环境。

Redis/RQ 在线探测结果：

```text
ConnectionError Error 10061 connecting to localhost:6379
```

说明：当前 `localhost:6379` Redis 服务未启动，因此本次没有完成真实 Redis 入队测试；但调度注册和 enqueue 参数已用假队列验证通过。

## 启动建议

启动 Redis 后，可分别启动：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
python backend\worker.py
```

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
python backend\scheduler_worker.py
```

FastAPI 和前端仍按原方式启动：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
uvicorn app.main:app --app-dir backend --reload --port 8088
```

```powershell
cd frontend
npm.cmd run dev
```

## 结论

V1 已具备按钮触发优先、定时扫描轻量补充的异步架构。当前代码侧验证通过；真实 Redis/RQ 端到端验证需要先启动 Redis 服务。
