# 风险扫描接入 RAG 测试记录

## 测试目标

验证风险扫描 Agent 已按架构流程接入 RAG：

- 规则引擎继续负责风险打分，不让大模型决定风险分。
- RAG 检索销售 SOP、价格策略和异议处理话术，作为大模型解释与建议的上下文。
- 检索结果写入 `rag_retrieval_trace`，风险证据写入 `rag_trace_id`、命中数和来源。
- 即使 LLM 不可用，也能使用确定性降级建议继续生成待人工审批任务草稿。
- 风险扫描流程增加 `retrieve_sales_knowledge` 节点，便于前端展示 Agent Trace。

## 测试环境

- 项目路径：`D:\insightpilot`
- Worker 函数：`backend/app/workers/risk_jobs.py::run_risk_scan`
- 测试向量库：Milvus Lite 本地文件 `backend/tests/rag_test_milvus.db`
- 测试 Embedding：关闭真实 DashScope 调用，使用确定性向量降级。
- 测试 LLM：清空 `deepseek_api_key`，验证 LLM 不可用时主流程仍可落库。
- MySQL：使用项目 `.env` 中配置的 `insightpilot` 数据库。

## 前置条件

已完成默认知识库入库：

- 文档切片：20 条
- QA 问答对：71 条
- 总计：91 条

## 执行命令

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
Remove-Item Env:MILVUS_URI -ErrorAction SilentlyContinue
$env:USE_REAL_EMBEDDING='false'

@'
import json
from sqlalchemy import text

from app.core.config import settings
settings.milvus_uri = 'D:/insightpilot/backend/tests/rag_test_milvus.db'
settings.use_real_embedding = False
settings.deepseek_api_key = ''

from app.core.database import SessionLocal
from app.workers.risk_jobs import run_risk_scan

result = run_risk_scan('demo_tenant', 'user_manager')
print({k: result[k] for k in ['run_id', 'status', 'risk_count', 'approval_count']})
print(result['items'][0] if result['items'] else None)

db = SessionLocal()
try:
    steps = db.execute(
        text('''
        SELECT node_name, tool_name, status, output_json
        FROM agent_step
        WHERE tenant_id = :tenant_id AND run_id = :run_id
        ORDER BY started_at ASC
        '''),
        {'tenant_id': 'demo_tenant', 'run_id': result['run_id']},
    ).mappings().all()
    for step in steps:
        print(step['node_name'], step['tool_name'], step['status'], json.loads(step['output_json']))

    risk = db.execute(
        text('''
        SELECT evidence_json
        FROM customer_risk_snapshot
        WHERE tenant_id = :tenant_id AND generated_by_run_id = :run_id
        ORDER BY created_at DESC
        LIMIT 1
        '''),
        {'tenant_id': 'demo_tenant', 'run_id': result['run_id']},
    ).mappings().first()
    evidence = json.loads(risk['evidence_json'])
    print({k: evidence.get(k) for k in ['rag_status', 'rag_trace_id', 'rag_hit_count']})
finally:
    db.close()
'@ | python
```

## 测试结果

本次执行结果：

- `run_id=run_485ec2fbc5e44abc`
- 扫描状态：`awaiting_approval`
- 风险客户数：4
- 审批草稿数：4
- 第一条结果：`customer_id=c_001`，`risk_score=100`，`risk_level=high`
- 第一条结果 RAG：`rag_trace_id=trace_131be5e59a9a4cb9`，`rag_hit_count=3`

Agent Step 结果：

- `load_crm_data`：成功，客户数 10，开放商机数 8。
- `calculate_rule_risk`：成功，风险候选数 4。
- `retrieve_sales_knowledge`：成功，检索 4 次，成功 4 次，失败 0 次。
- `generate_task_draft`：成功，创建审批草稿 4 条。

风险证据校验：

- `evidence_json.rag_status=success`
- `evidence_json.rag_trace_id` 有值
- `evidence_json.rag_hit_count=3`

## 结论

风险扫描 Agent 已完成“规则引擎打底 + RAG 增强 + LLM 解释建议 + 人工审批”的核心闭环。当前实现保持了降级能力：即使 LLM 不可用，系统仍能生成可审批的任务草稿；后续如果 Milvus 或 Embedding 服务异常，风险扫描也会记录 RAG 失败原因并继续主流程。
