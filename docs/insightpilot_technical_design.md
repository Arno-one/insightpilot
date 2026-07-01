# InsightPilot 技术方案文档

版本：v1.0
项目名称：InsightPilot
技术定位：单体 FastAPI 模块化项目，预留 SaaS、多服务和多 Agent 演进能力。

## 一、技术决策总览

| 方向 | 决策 |
|---|---|
| 后端 | FastAPI |
| ORM | SQLAlchemy |
| 数据库 | MySQL |
| 迁移 | Alembic |
| 初始化 | 保留 `init_schema.sql` 和 `seed_demo_data.sql` |
| 前端 | Next.js / React |
| UI 风格 | SaaS 工作台 |
| 登录 | JWT |
| 权限 | RBAC |
| Agent 编排 | LangGraph |
| RAG 向量库 | Milvus Docker |
| LLM | DeepSeek |
| Embedding | DashScope |
| 缓存 | Redis |
| 队列 | RQ |
| 定时任务 | APScheduler 轻量触发 |
| 架构形态 | V1 模块化单体，后期拆服务 |
| 多租户 | V1 预留 `tenant_id`，不做完整租户系统 |

## 二、系统架构

```text
Next.js SaaS 工作台
  ↓
FastAPI API 层
  ↓
模块化业务层
  ├─ Auth / RBAC
  ├─ CRM
  ├─ Risk
  ├─ Agent / LangGraph
  ├─ RAG
  ├─ Approval
  ├─ Task
  └─ Report
  ↓
基础设施层
  ├─ MySQL：业务数据、权限、任务、日志、RAG 元信息
  ├─ Milvus：文档切片和 QA 向量检索
  ├─ Redis：缓存、RQ 队列、Agent 临时状态
  ├─ DeepSeek：LLM 生成
  └─ DashScope：Embedding
```

## 三、后端模块结构

建议项目结构：

```text
backend/
  app/
    main.py
    core/
      config.py
      database.py
      redis.py
      queue.py
      security.py
      logging.py
      exceptions.py
    shared/
      response.py
      pagination.py
      ids.py
      time.py
    modules/
      auth/
        models.py
        schemas.py
        repository.py
        service.py
        router.py
        permissions.py
      crm/
        models.py
        schemas.py
        repository.py
        service.py
        router.py
      risk/
        models.py
        schemas.py
        rules.py
        engine.py
        repository.py
        service.py
        router.py
      agent/
        models.py
        schemas.py
        graphs/
          risk_analysis_graph.py
          business_report_graph.py
        tools/
          crm_tools.py
          risk_tools.py
          rag_tools.py
          approval_tools.py
        repository.py
        service.py
        router.py
      rag/
        models.py
        schemas.py
        milvus_client.py
        embedding_client.py
        chunking.py
        ingestion_service.py
        retrieval_service.py
        rerank_service.py
        evaluation_service.py
        cache_service.py
        router.py
      approval/
        models.py
        schemas.py
        repository.py
        service.py
        router.py
      task/
        models.py
        schemas.py
        repository.py
        service.py
        router.py
      report/
        models.py
        schemas.py
        repository.py
        service.py
        router.py
    workers/
      rag_jobs.py
      risk_jobs.py
      report_jobs.py
    seed/
      demo_data.py
    scheduler.py
  alembic/
  scripts/
    init_schema.sql
    seed_demo_data.sql
  worker.py
  requirements.txt
```

分层规则：

- `router.py` 只处理 HTTP 入参、权限依赖和响应。
- `service.py` 处理业务流程。
- `repository.py` 只处理数据库读写。
- `models.py` 定义 SQLAlchemy ORM。
- `schemas.py` 定义 Pydantic 请求和响应。
- `tools/` 中的 Agent Tool 必须声明 required_permissions。
- 所有复杂逻辑尽量沉到可测试的深模块。

## 四、前端结构

建议项目结构：

```text
frontend/
  app/
    login/
    dashboard/
    risks/
    approvals/
    tasks/
    reports/
    agent-trace/
  components/
    layout/
    charts/
    risk/
    approval/
    agent/
    ui/
  lib/
    api.ts
    auth.ts
    permissions.ts
    token.ts
  styles/
```

页面：

- 登录页。
- 经营驾驶舱。
- 客户风险中心。
- AI 任务审批台。
- 我的任务 / 团队任务。
- 经营报告。
- Agent 执行追踪。

前端权限：

- 登录后保存 JWT。
- API 请求自动带 `Authorization: Bearer token`。
- 菜单根据权限渲染。
- 按钮根据权限渲染。
- 403 页面清晰展示无权限原因。

## 五、数据库设计

完整 ER 见：

- `insightpilot_er_design.md`

关键原则：

- 不使用数据库外键。
- 使用同名字段隐性关联。
- 所有关联字段建立普通索引。
- 所有核心表预留 `tenant_id`。
- V1 默认 `tenant_id = demo_tenant`。

核心表：

- `tenant`
- `sys_user`
- `sys_role`
- `sys_permission`
- `sys_user_role`
- `sys_role_permission`
- `crm_customer`
- `crm_contact`
- `crm_deal`
- `crm_follow_up_record`
- `customer_risk_snapshot`
- `risk_rule_config`
- `approval_record`
- `sales_task`
- `agent_run`
- `agent_step`
- `business_report`
- `rag_document`
- `rag_chunk`
- `rag_qa_pair`
- `rag_ingest_job`
- `rag_retrieval_trace`
- `rag_retrieval_hit`

## 六、初始化与迁移策略

V1 使用双轨制：

```text
Alembic：负责后续结构演进
init_schema.sql：负责本地一键建表
seed_demo_data.sql：负责插入模拟数据
```

首次初始化流程：

```text
1. 创建 MySQL 数据库 insightpilot
2. 执行 scripts/init_schema.sql
3. 执行 scripts/seed_demo_data.sql
4. 执行 alembic stamp head
5. 启动 FastAPI
6. 启动 RQ Worker
7. 启动 Next.js 前端
```

后续迭代流程：

```text
1. 修改 SQLAlchemy Model
2. 生成 Alembic migration
3. 审查 migration
4. 执行 alembic upgrade head
5. 如有必要同步更新 init_schema.sql
```

## 七、RAG 架构

RAG 全流程按用户提供的高级架构文档执行。

### 离线入库

```text
原始 Markdown / QA JSONL
  → 文档切片 chunk_size=500, overlap=50
  → 批量 Embedding
  → Milvus 双 Collection 入库
  → MySQL 元信息入库
  → 标量索引
  → load_collection
```

Milvus Collection：

```text
insightpilot_document_chunks
insightpilot_qa_pairs
```

`insightpilot_document_chunks` 字段：

- `pk`
- `tenant_id`
- `doc_id`
- `section_id`
- `category`
- `title`
- `text`
- `chunk_index`
- `source_file`
- `source_type`
- `created_at`
- `dense_vector`
- `sparse_vector`

`insightpilot_qa_pairs` 字段：

- `pk`
- `tenant_id`
- `qa_id`
- `doc_id`
- `section_id`
- `question`
- `answer`
- `tags`
- `search_text`
- `source_type`
- `created_at`
- `dense_vector`
- `sparse_vector`

QA 的 `search_text`：

```text
question + answer + tags
```

### 在线检索

```text
用户问题
  → 缓存检查
  → Query Rewrite
  → 生成 query_vector
  → document_chunks + qa_pairs 并行混合检索
  → RRF 融合
  → CrossEncoder 精排
  → Token 预算控制
  → 去重
  → 来源标记
  → LLM 生成答案
  → trace 日志
```

### RAG 缓存

Redis 缓存：

- Query Rewrite：TTL 1 天。
- Query Embedding：TTL 7 天。
- Retrieval Result：TTL 10-30 分钟。

### RAG 降级

```text
Embedding API 不可用
  → 尝试本地同维模型
  → 不可用则纯 BM25

LLM 不可用
  → 返回检索结果摘要和来源
```

### RAG 评估

指标：

- Recall@K。
- MRR。
- NDCG。
- Hit Rate。

Trace 字段：

- original_query。
- rewritten_query。
- rewrite_ms。
- embed_ms。
- search_ms。
- rerank_ms。
- total_ms。
- recalled_ids。
- hit_count。

## 八、LangGraph Agent 设计

V1 直接引入 LangGraph。

### 风险分析图

节点：

```text
load_crm_data
calculate_rule_risk
retrieve_sales_knowledge
generate_risk_reason
generate_task_draft
create_approval_record
save_run_result
```

状态对象建议：

```text
tenant_id
user_id
scope
customers
risk_results
rag_context
task_drafts
approval_records
errors
```

关键规则：

- `calculate_rule_risk` 不调用 LLM。
- 风险分由规则引擎确定。
- LLM 只负责解释、建议和话术。
- 任何任务创建都先进入审批。

### 经营日报图

节点：

```text
load_metrics
load_risk_summary
retrieve_report_knowledge
generate_report
save_business_report
```

关键规则：

- 报告必须先结论后原因。
- 必须突出高风险客户和建议动作。
- 报告生成结果落入 `business_report`。

### Agent Tool 权限

每个工具声明：

```text
tool_name
description
required_permissions
input_schema
output_schema
danger_level
requires_approval
```

执行前检查：

```text
当前用户权限集合
  → 是否包含 required_permissions
  → 是否需要人工审批
  → 写入 agent_step
```

## 九、风险规则引擎

V1 代码内置规则，数据库预留 `risk_rule_config`。

初始规则：

| 规则 | 分数 |
|---|---:|
| 超过 14 天未跟进 | +20 |
| 超过 30 天未跟进 | +35 |
| 报价后超过 7 天未回应 | +20 |
| 报价后超过 14 天未回应 | +35 |
| 阶段停留超过 21 天 | +15 |
| 最近一次跟进情绪负面 | +15 |
| 竞品介入 | +20 |
| 预算不匹配 | +10 |
| 商机金额较高 | +10 |
| 下次跟进时间为空 | +10 |

风险等级：

```text
0-39：low
40-69：medium
70-100：high
```

输出结构：

```text
risk_score
risk_level
rule_hits
evidence
```

## 十、异步任务与定时任务

RQ 任务：

- `rag_ingest_job`
- `risk_scan_job`
- `business_report_job`

按钮触发：

```text
用户点击生成风险分析
  → 创建 RQ Job
  → 立即返回 job_id
  → 前端轮询状态
```

定时触发：

```text
每天 08:30 风险扫描
每天 18:00 经营日报
```

V1 使用 APScheduler 轻量调度，后期可升级 Celery Beat 或独立调度服务。

## 十一、模拟数据设计

V1 必须内置模拟数据，确保开箱可演示。

数据量：

- 1 个租户。
- 3 个角色。
- 3-5 个用户。
- 30-50 个客户。
- 每个客户 1-2 个联系人。
- 每个客户 0-1 个商机。
- 每个客户 1-5 条跟进记录。
- 至少 10 个中高风险客户。
- 至少 5 个报价后无回应客户。
- 至少 3 个竞品介入客户。
- 至少 5 条待审批 AI 任务草稿。

账号建议：

```text
owner / Owner@123456
manager / Manager@123456
sales01 / Sales@123456
sales02 / Sales@123456
sales03 / Sales@123456
```

数据覆盖：

- 正常推进客户。
- 报价后沉默客户。
- 预算不足客户。
- 竞品介入客户。
- 负面情绪客户。
- 高金额客户。
- 已成交客户。
- 流失客户。

## 十二、API 设计概览

认证：

```text
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
```

CRM：

```text
GET  /api/crm/customers
GET  /api/crm/customers/{customer_id}
POST /api/crm/follow-ups
GET  /api/crm/deals
```

风险：

```text
POST /api/risk/scan
GET  /api/risk/snapshots
GET  /api/risk/snapshots/{risk_snapshot_id}
```

审批：

```text
GET  /api/approvals
POST /api/approvals/{approval_id}/approve
POST /api/approvals/{approval_id}/reject
POST /api/approvals/{approval_id}/approve-with-changes
```

任务：

```text
GET   /api/tasks
PATCH /api/tasks/{task_id}/status
```

报告：

```text
POST /api/reports/daily/generate
GET  /api/reports
GET  /api/reports/{report_id}
```

Agent：

```text
GET /api/agent/runs
GET /api/agent/runs/{run_id}
GET /api/agent/runs/{run_id}/steps
```

RAG：

```text
POST /api/rag/ingest
POST /api/rag/search
GET  /api/rag/traces
GET  /api/rag/traces/{trace_id}
```

Job：

```text
GET /api/jobs/{job_id}
```

## 十三、可观测性

必须记录：

- 请求日志。
- SQL 慢查询预留。
- RQ Job 状态。
- Agent Run。
- Agent Step。
- RAG Trace。
- RAG Hit。
- LLM 调用耗时。
- Embedding 调用耗时。

前端可视化：

- Agent 执行链路。
- 节点状态。
- 工具调用输入输出摘要。
- RAG 命中来源。
- 总耗时。

## 十四、测试策略

单元测试：

- 风险规则引擎。
- 权限判断。
- ID 生成。
- RAG JSONL 校验。

集成测试：

- 登录获取 JWT。
- 销售员访问全局风险被拒绝。
- 主管审批任务草稿后生成销售任务。
- 风险扫描生成风险快照。
- 经营日报生成报告。

端到端测试：

- 登录。
- 触发风险扫描。
- 查看风险客户。
- 审批任务。
- 销售员查看任务。
- 生成日报。

RAG 评估：

- 固定 QA 查询集。
- 对比纯向量、纯 BM25、RRF、RRF + CrossEncoder。
- 输出 Recall@K、MRR、NDCG。

## 十五、后期拆服务路线

V1：

```text
模块化单体
```

V2：

```text
RAG 服务独立
```

V3：

```text
Agent 编排服务独立
```

V4：

```text
报表和异步任务服务独立
```

V5：

```text
多租户 SaaS 平台化
```

拆分原则：

- 先按业务稳定性拆，不按技术冲动拆。
- RAG 和 Agent 是最适合优先独立的两个服务。
- Auth 和核心 CRM 在早期保持在主服务中，降低联调复杂度。

## 十六、开发顺序建议

推荐顺序：

1. 项目骨架。
2. 配置、日志、数据库、Redis。
3. SQLAlchemy Model + init SQL + seed SQL。
4. Auth + JWT + RBAC。
5. CRM 查询接口和模拟数据。
6. 风险规则引擎。
7. RAG 入库和检索。
8. LangGraph 风险分析图。
9. 审批和销售任务。
10. 经营日报。
11. 前端登录和工作台。
12. Agent Trace 页面。
13. RQ Worker 和定时任务。
14. 测试和演示脚本。

## 十七、关键风险与规避

### 1. 一开始做太大

风险：项目变成全业务平台，迟迟不能演示。

规避：V1 只做客户流失风险闭环。

### 2. 让 LLM 直接打分

风险：结果不可复现，不适合企业系统。

规避：规则引擎打分，LLM 解释和建议。

### 3. AI 直接创建任务

风险：错误动作影响业务。

规避：AI 只生成草稿，主管审批后创建任务。

### 4. RAG 只做向量检索

风险：关键词和高频问答命中不稳定。

规避：双 Collection、BM25、RRF、CrossEncoder、QA 优先。

### 5. 权限只做前端隐藏

风险：接口和 Agent Tool 可能越权。

规避：前端、后端、Agent Tool 三层校验。

### 6. 没有可观测性

风险：Agent 出错无法解释。

规避：Agent Run、Agent Step、RAG Trace 全链路落库。

