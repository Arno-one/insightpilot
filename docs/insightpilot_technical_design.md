# InsightPilot 技术方案文档

版本：2026-07-01
定位：基于 FastAPI + Next.js 的模块化单体销售运营 Agent 系统

## 1. 文档目标

本文不再描述理想化全景蓝图，而是聚焦当前真实技术实现：

- 系统已经有哪些模块和边界
- 数据库和初始化策略如何落地
- 风险扫描、RAG、审批、报告目前是怎么串起来的
- `LangGraph` 当前已经接管了哪些链路，还剩哪些图待迁移

## 2. 技术栈

| 方向 | 当前方案 |
|---|---|
| 后端 | FastAPI |
| 前端 | Next.js / React |
| ORM | SQLAlchemy 2 |
| 数据库 | MySQL |
| 迁移 | Alembic |
| 缓存 / 队列 | Redis + RQ |
| 定时任务 | APScheduler |
| 向量检索 | Milvus |
| LLM / 结构化输出 | OpenAI SDK 接 DeepSeek |
| Embedding | DashScope |
| Agent 编排 | `langgraph` 已引入，风险图待正式落地 |

## 3. 系统架构

```text
Next.js 前端工作台
  -> FastAPI API 层
  -> 模块化业务层
     -> Auth / CRM / Risk / Approval / Task / Report / Agent / RAG
  -> 基础设施层
     -> MySQL
     -> Redis / RQ
     -> Milvus
     -> LLM / Embedding 服务
```

当前版本仍采用模块化单体，原因有两个：

- 业务闭环还在快速收敛阶段，单体更利于联调和演示
- Agent、RAG、报表都还没稳定到值得独立拆服务的程度

## 4. 目录结构

当前关键目录如下：

```text
backend/
  app/
    core/
    modules/
      auth/
      crm/
      risk/
      approval/
      task/
      report/
      rag/
      agent/
        graphs/
    workers/
      risk_jobs.py
      report_jobs.py
      rag_jobs.py
  alembic/
  scripts/
    init_schema.sql
    seed_demo_data.sql
  worker.py
  scheduler_worker.py

frontend/
  app/
    login/
    dashboard/
    risks/
    approvals/
    tasks/
    reports/
    agent-trace/
    rag-evaluation/
  components/
    layout/
    ui/
```

## 5. 模块职责

### 5.1 后端模块

- `auth`
  登录、JWT、当前用户解析、权限依赖。
- `crm`
  客户列表查询与销售上下文数据读取。
- `risk`
  风险扫描入口、风险快照查询、规则引擎。
- `approval`
  AI 草稿审批、驳回、修改后审批通过。
- `task`
  销售任务列表查询。
- `report`
  经营日报触发与列表查询。
- `rag`
  入库、检索、评估、Trace 记录。
- `agent`
  Agent Run / Step 审计与图编排预留。

### 5.2 前端页面

- `dashboard`
  管理者经营驾驶舱，汇总风险、审批、执行、日报信号。
- `risks`
  风险客户列表、风险原因、AI 建议和处理状态。
- `approvals`
  AI 草稿审批台。
- `tasks`
  正式销售任务页。
- `reports`
  经营报告列表。
- `agent-trace`
  Agent Run、Step、RAG 命中审计页。
- `rag-evaluation`
  RAG 评估页。

## 6. 数据库设计原则

当前数据库策略已经明确，不再反复摇摆：

### 6.1 不设置外键

所有核心表都不使用数据库外键约束，只通过同名字段做隐式关联。

这样做的原因：

- 演示环境重建更轻
- 迁移和导数更灵活
- 便于后续把部分模块拆成独立服务

### 6.2 通过索引保证查询效率

虽然不设外键，但对这些字段都要建普通索引：

- `tenant_id`
- `user_id`
- `customer_id`
- `deal_id`
- `approval_id`
- `run_id`
- `trace_id`

### 6.3 所有核心表补中文注释

当前数据库基线已经完成两件事：

- 表注释齐全
- 字段注释齐全

这意味着后续无论是开发、演示还是手工查数，都不用再猜字段含义。

## 7. 初始化与迁移策略

当前采用“双轨制”：

```text
init_schema.sql
  -> 本地快速重建演示数据库

seed_demo_data.sql
  -> 注入真实模拟数据

Alembic baseline revision
  -> 管理后续结构迭代
```

当前已落地的关键文件：

- `backend/scripts/init_schema.sql`
- `backend/scripts/seed_demo_data.sql`
- `backend/alembic/versions/20260701_0001_init_schema_with_comments.py`

推荐初始化流程：

```text
1. 创建数据库
2. 执行 init_schema.sql
3. 执行 seed_demo_data.sql
4. 执行 alembic stamp head
5. 启动 FastAPI
6. 启动 RQ Worker
7. 启动前端
```

## 8. 风险扫描当前实现

### 8.1 当前执行形态

风险扫描现在已经迁移到真实 `LangGraph` 图。

当前职责拆分为：

- `backend/app/modules/agent/graphs/risk_analysis_graph.py`
  负责状态对象、节点函数、图编排和工作流执行。
- `backend/app/workers/risk_jobs.py`
  只保留 RQ Worker 入口，转调图工作流。

当前流程大致如下：

```text
创建 agent_run
  -> load_crm_data
  -> calculate_rule_risk
  -> retrieve_sales_knowledge
  -> generate_task_draft
  -> persist_agent_trace
```

### 8.2 当前节点口径

前端 Agent Trace 已经依赖这些节点名展示：

- `load_crm_data`
- `calculate_rule_risk`
- `retrieve_sales_knowledge`
- `generate_task_draft`

下一步迁图时要尽量保持兼容，避免前端 Trace 认知断层。

### 8.3 当前核心原则

- 风险分由规则引擎计算，不交给 LLM。
- RAG 是增强链路，失败时要降级，不能阻断主流程。
- AI 只生成建议和草稿，不能直接落正式任务。
- 所有关键执行步骤都要落 `agent_step`。

## 9. 经营日报当前实现

经营日报目前仍然是 Worker 顺序流。

当前能力包括：

- 聚合客户、商机、风险、审批、任务等指标
- 生成摘要与建议
- 写入 `business_report`
- 把关键执行步骤同步写入 Agent Trace

后续它也会迁到 `LangGraph`，但不是下一轮优先级。

## 10. RAG 架构现状

### 10.1 当前链路

```text
原始 Markdown / QA
  -> 切片或标准化
  -> Embedding
  -> Milvus 入库
  -> MySQL 记录元信息
  -> 查询时执行混合检索
  -> RRF 融合
  -> 重排
  -> 记录 rag_retrieval_trace 与 rag_retrieval_hit
```

### 10.2 当前落库表

- `rag_document`
- `rag_chunk`
- `rag_qa_pair`
- `rag_ingest_job`
- `rag_retrieval_trace`
- `rag_retrieval_hit`

### 10.3 当前角色

RAG 在系统里不是独立产品，而是风险扫描和经营报告的知识增强层。

它主要回答三类问题：

- 当前风险客户适合参考什么销售 SOP
- 面对预算、竞品、拖延、负面情绪时该怎么解释
- 在日报总结里应该优先强调哪些动作建议

## 11. 可观测设计

当前系统重点可观测对象有三类：

### 11.1 Agent 执行

- `agent_run`
- `agent_step`

用于回答：

- 谁触发了任务
- 任务最终成功、失败还是等待审批
- 每个节点耗时多久
- 哪一步出错

### 11.2 RAG 检索

- `rag_retrieval_trace`
- `rag_retrieval_hit`

用于回答：

- 原始问题是什么
- 查询是否被改写
- 命中了哪些来源
- 哪些文档或 QA 被引用

### 11.3 业务结果

- `customer_risk_snapshot`
- `approval_record`
- `sales_task`
- `business_report`

用于回答：

- 风险判断最后有没有进入业务动作
- 审批是否积压
- 建议有没有落地成任务
- 日报是否真的反映当天风险态势

## 12. 当前已知技术边界

### 12.1 `LangGraph` 已部分落地

当前状态是：

- 风险扫描图已经完成落地
- `risk_jobs.py` 已缩成 Worker 入口
- `business_report_graph.py` 仍是占位，日报链路还没切图

### 12.2 Worker 文件仍偏大

`risk_jobs.py` 当前承担了太多职责：

- 读数
- 规则计算
- RAG 调用
- 风险快照落库
- 审批草稿落库
- Agent Step 记录

这也是下一步迁图时必须顺手拆模块的原因。

### 12.3 任务闭环仍不完整

当前任务已经能创建和查询，但不是完整执行系统。

## 13. 后续技术演进候选

风险扫描图完成后，后续更值得继续推进的方向是：

- 把经营日报迁到 `LangGraph`
- 继续补强失败链路可观测性
- 补销售任务执行闭环
- 做全链路回归验证，确认前端 Trace、审批和报告继续兼容

## 14. 一句话结论

当前技术方案已经从“先画蓝图”进入“让关键链路真实图编排化”的阶段。数据库基线、RAG、审批、任务、日报、Trace 都已经形成闭环，风险扫描图也已落地，后续重点会转向经营日报图和更完整的执行闭环。
