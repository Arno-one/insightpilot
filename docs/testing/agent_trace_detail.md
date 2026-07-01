# Agent Trace 详情测试记录

## 测试目标

验证 Agent Trace 从 Run 列表升级为可审计详情链路：

- 后端新增 `GET /api/agent/runs/{run_id}`。
- 接口返回 Agent Run、Agent Step、Step 输出 JSON。
- 对风险扫描 Run，可从 `retrieve_sales_knowledge` Step 中提取 RAG trace，并返回 RAG 命中片段。
- 前端 `/agent-trace` 支持 Run 列表和详情面板联动。
- 前端详情展示 Step 时间线、工具名、耗时、输出 JSON 和 RAG Evidence。

## 后端接口测试

执行命令：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
login = client.post('/api/auth/login', json={'username': 'owner', 'password': 'Owner@123456'})
token = login.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

runs = client.get('/api/agent/runs', headers=headers).json()['data']
risk_run = next(item for item in runs if item['run_type'] == 'risk_analysis')
detail = client.get(f"/api/agent/runs/{risk_run['run_id']}", headers=headers).json()['data']

print(risk_run['run_id'])
print([step['node_name'] for step in detail['steps']])
print(len(detail['rag_traces']))
print(len(detail['rag_traces'][0]['hits']) if detail['rag_traces'] else 0)
'@ | python
```

测试结果：

- 登录：`owner / Owner@123456` 成功。
- Run 列表接口：HTTP 200，业务码 200。
- 风险扫描 Run：`run_485ec2fbc5e44abc`。
- Step 顺序：
  - `load_crm_data`
  - `calculate_rule_risk`
  - `retrieve_sales_knowledge`
  - `generate_task_draft`
- RAG Trace 数量：4。
- 第一条 RAG Trace 命中数：3。

## 构建测试

后端编译：

```powershell
python -m compileall backend/app -q
```

前端构建：

```powershell
npm.cmd run build
```

测试结果：

- 后端编译通过。
- Next.js 生产构建通过。
- `/agent-trace` 页面构建成功。

## 结论

Agent Trace 详情链路已可用。现在系统可以从一次 Agent Run 追踪到每个执行节点，再追踪到 RAG 检索来源和命中片段，满足 V1 对“可解释、可审计、可展示”的核心要求。
