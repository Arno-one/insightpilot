# InsightPilot 当前版本状态与下一版本路线图

版本日期：2026-07-01

## 1. 文档目的

本文只回答三件事：

- 当前版本到底已经做到了什么
- 当前版本哪些能力还没有真正落地
- 下一版本我们只优先推进什么

这份文档已经按当前代码、数据库基线和前端页面的真实状态更新，不再保留旧的乱码问题描述和过期判断。

## 2. 当前版本定位

InsightPilot 当前版本已经不是“纯骨架”，而是一个可演示、可追踪、可审计的销售运营 Agent Demo。

当前主链路如下：

```text
CRM 客户 / 商机 / 跟进数据
  -> 规则引擎识别客户风险
  -> RAG 检索销售 SOP / 产品资料 / 异议处理话术
  -> LLM 生成风险解释、建议和推荐话术
  -> 写入风险快照与审批草稿
  -> 主管审批后创建正式销售任务
  -> 经营日报汇总风险、审批和任务情况
  -> Agent Trace 回看执行步骤与 RAG 命中来源
```

它的定位依然是 V1 Demo，但已经具备比较完整的“业务闭环 + 工程落点 + 可观测性”。

## 3. 当前版本已完成的能力

### 3.1 基础工程

- 后端采用模块化单体 `FastAPI`。
- 前端采用 `Next.js` 工作台结构。
- 已接入 `MySQL`、`SQLAlchemy`、`Redis`、`RQ`、`APScheduler`、`pymilvus`、`OpenAI/DeepSeek`、`DashScope Embedding`。
- Worker 启动入口已存在：
  - `backend/worker.py`
  - `backend/scheduler_worker.py`

### 3.2 数据库基线

- 已完成 `init_schema.sql` 重建。
- 已完成 `seed_demo_data.sql` 重建。
- 已补齐中文表注释和字段注释。
- 已生成首个 Alembic baseline revision：
  - `backend/alembic/versions/20260701_0001_init_schema_with_comments.py`
- 已明确执行以下建模约束：
  - 不设置数据库外键
  - 通过同名字段进行表关联
  - 重要关联字段使用普通索引

### 3.3 演示数据

- 已替换旧的脏数据和乱码数据。
- 当前模拟数据覆盖：
  - 租户、用户、角色、权限
  - 客户、联系人、商机、跟进记录
  - 风险快照、审批记录、销售任务
  - Agent Run、Agent Step
  - RAG Trace、RAG Hit
  - 经营日报
- 数据内容更接近真实销售场景，不再只是随机占位。

### 3.4 登录与权限

- 已实现账号密码登录。
- 已实现 JWT 鉴权。
- 已实现 RBAC 权限校验。
- 已支持 `owner`、`manager`、`salesperson` 三类角色视角。
- 前后端都已按权限控制菜单、按钮和接口访问。

### 3.5 CRM 与风险分析

- 已实现客户列表查询。
- 已实现规则引擎风险识别。
- 已支持典型风险信号：
  - 长时间未跟进
  - 报价后无回应
  - 客户负面情绪
  - 竞品介入
  - 缺少下一步跟进时间
  - 高金额商机
- 已落库 `customer_risk_snapshot` 风险快照。

### 3.6 RAG 知识库

- 已实现 Markdown 文档切片入库。
- 已实现 QA 对入库。
- 已使用双 Collection：
  - `insightpilot_document_chunks`
  - `insightpilot_qa_pairs`
- 已实现混合检索、RRF 融合、精排与 Trace 记录。
- 已开放：
  - RAG 检索接口
  - RAG 入库任务
  - RAG 评估接口
- 前端已接入 RAG 评估页。

### 3.7 风险建议与审批

- 风险分仍由规则引擎决定，不交给 LLM。
- LLM 只负责：
  - 风险解释
  - 行动建议
  - 推荐话术
- 已实现 AI 草稿审批列表。
- 已实现：
  - 审批通过
  - 审批驳回
  - 修改后审批通过
- 审批通过后才会创建正式销售任务。

### 3.8 任务、报告与可观测

- 已实现销售任务列表。
- 已实现经营日报生成 Worker 与报告列表。
- 已实现 Agent Run 列表与详情。
- 已实现 Agent Step 时间线。
- 已实现 RAG Trace 与命中详情串联。
- 前端已完成以下页面接入：
  - 经营驾驶舱
  - 风险中心
  - AI 审批台
  - 销售任务
  - 经营报告
  - Agent Trace
  - RAG 评估

## 4. 当前版本未完成但已预留的能力

### 4.1 LangGraph 仍未正式接管执行链路

当前 `langgraph` 依赖已安装，但下面两个文件仍是占位实现：

- `backend/app/modules/agent/graphs/risk_analysis_graph.py`
- `backend/app/modules/agent/graphs/business_report_graph.py`

也就是说：

- 风险扫描目前还是 `risk_jobs.py` 顺序流
- 经营日报目前还是 `report_jobs.py` 顺序流
- `agent_step` 已经在记录节点，但还不是由真实图编排驱动

### 4.2 任务执行闭环还不完整

当前任务模块已经能承接审批结果，但还没有完整实现：

- 任务状态流转更新
- 执行结果填写
- 逾期标记
- 任务反向影响客户状态

### 4.3 CSV 导入还没开始

当前系统仍以演示数据为主，尚未支持 CRM 数据导入。

### 4.4 报表与客户详情页还偏轻

- 报表以日报为主，周报和趋势分析还没开始
- 风险中心当前更偏列表页，还没有完整客户详情上下文页

## 5. 下一版本只聚焦一件事

下一版本先做：

- `LangGraph` 风险扫描图

本轮不同时铺开经营日报图、CSV 导入、客户详情、报表增强，原因很简单：

- 风险扫描链路已经是当前系统最核心、最可展示的 Agent 主链路
- 前端 Agent Trace 已经依赖现有 `agent_run / agent_step / rag_traces` 结构
- 现在最有价值的是把“已有能力”从顺序流升级为真实图编排，而不是再加新页面

## 6. 风险扫描图的落地方向

下一版本的目标不是机械把顺序函数搬进图，而是边迁移边做模块化拆分。

建议节点口径如下：

```text
load_crm_data
  -> calculate_rule_risk
  -> retrieve_sales_knowledge
  -> generate_risk_reason / create_approval_record
  -> persist_agent_trace
```

实际落地时需要满足以下约束：

- 保留当前接口输出结构
- 保留现有数据库表结构
- 保留当前审批草稿和风险快照落库行为
- 保留 Agent Trace 页面依赖的核心节点名
- 把 `risk_jobs.py` 拆成更清晰的状态对象、节点函数和图构建入口

## 7. 下一版本验收标准

只要满足下面 6 条，就算这一轮做成：

1. 风险扫描由 Worker 调用真实 `LangGraph` 图，而不是手写顺序流。
2. `agent_run`、`agent_step`、`rag_retrieval_trace` 的写入结果保持兼容。
3. 前端 Agent Trace 页面无需改接口即可继续展示。
4. 出错节点可以在图执行中被清晰定位。
5. `risk_jobs.py` 不再维持当前这种单文件大流程堆叠。
6. 文档与代码状态保持一致。

## 8. 当前版本演示顺序

如果现在要演示项目，推荐按下面顺序：

1. 使用 `owner` 或 `manager` 登录。
2. 先看经营驾驶舱，解释今天的风险、审批和执行信号。
3. 触发风险扫描任务。
4. 查看风险中心里的高风险客户和建议。
5. 进入审批台，通过或驳回一条 AI 草稿。
6. 到任务页查看正式销售任务。
7. 生成日报并查看结果。
8. 最后打开 Agent Trace，展示每一步的执行和 RAG 来源。

## 9. 一句话结论

当前版本的重心已经从“补骨架”切到“做真实 Agent 编排”。数据库基线、演示数据、前端工作台和可观测链路都已经具备，下一步最值得投入的就是把风险扫描正式迁到 `LangGraph`。
