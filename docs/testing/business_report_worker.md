# 经营日报 Worker 测试记录

## 测试目标

验证 InsightPilot V1 经营日报模块完成真实闭环：

- Worker 不再是占位实现，可以创建 `agent_run`。
- 能聚合客户、商机、风险、审批和任务指标。
- 能读取每个客户最新风险快照 Top 列表，避免同一客户因多次扫描重复上榜。
- 能生成日报摘要和经营建议；LLM 不可用时自动使用规则模板降级。
- 能写入 `business_report`，并通过 `/api/reports` 查询接口读取。

## 测试环境

- 项目路径：`D:\insightpilot`
- Worker 函数：`backend/app/workers/report_jobs.py::generate_daily_report`
- API 路由：`GET /api/reports`
- MySQL：使用项目 `.env` 中配置的 `insightpilot` 数据库。
- LLM：测试时清空 `deepseek_api_key`，验证降级链路。

## 执行命令

后端编译检查：

```powershell
python -m compileall backend/app -q
```

Worker 级测试：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
import json
from sqlalchemy import text

from app.core.config import settings
settings.deepseek_api_key = ''

from app.core.database import SessionLocal
from app.workers.report_jobs import generate_daily_report

result = generate_daily_report('demo_tenant', 'u_owner_001')
print({k: result[k] for k in ['run_id', 'status', 'report_id', 'report_date', 'risk_top_count']})
print(result['metrics'])

db = SessionLocal()
try:
    steps = db.execute(
        text('''
        SELECT node_name
        FROM agent_step
        WHERE tenant_id = :tenant_id AND run_id = :run_id
        ORDER BY started_at ASC
        '''),
        {'tenant_id': 'demo_tenant', 'run_id': result['run_id']},
    ).scalars().all()
    print(list(steps))

    report = db.execute(
        text('''
        SELECT report_id, summary, suggestions
        FROM business_report
        WHERE tenant_id = :tenant_id AND report_id = :report_id
        LIMIT 1
        '''),
        {'tenant_id': 'demo_tenant', 'report_id': result['report_id']},
    ).mappings().first()
    print(report is not None)
finally:
    db.close()
'@ | python
```

接口级测试：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
from fastapi.testclient import TestClient
from app.core.config import settings
settings.deepseek_api_key = ''
from app.main import app

client = TestClient(app)
login = client.post('/api/auth/login', json={'username': 'owner', 'password': 'Owner@123456'})
token = login.json()['data']['token']
resp = client.get('/api/reports', headers={'Authorization': f'Bearer {token}'})
print(resp.status_code, resp.json()['code'], resp.json()['total'])
print(resp.json()['data'][0]['report_id'])
'@ | python
```

## 测试结果

Worker 级结果：

- `run_id=run_47b4385ebde74c0a`
- `status=success`
- `report_id=report_e249c671e36c4f19`
- `report_date=2026-07-01`
- `risk_top_count=4`

核心指标：

- 客户总数：12
- 在跟客户：10
- 报价阶段客户：4
- 竞品介入客户：3
- 开放商机：8
- 开放商机金额：828000.0
- 中风险客户：1
- 高风险客户：3
- 待审批 AI 任务：9
- 活跃任务：4
- 逾期任务：0

Agent Step 结果：

- `collect_business_metrics`
- `analyze_risk_top`
- `generate_report_narrative`
- `persist_business_report`

接口级结果：

- `owner / Owner@123456` 登录成功。
- `GET /api/reports` 返回 HTTP 200、业务码 200。
- 返回总数：3。
- 第一条为最新日报：`report_e249c671e36c4f19`。

## 结论

经营日报 Worker 已从占位实现升级为真实可用模块。当前版本已经满足 V1 的日报生成、Agent Trace、报表落库和接口查询闭环；后续可以继续把节点迁移到 LangGraph 显式编排，并增加周报、团队维度拆分和趋势对比。
