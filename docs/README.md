# InsightPilot 文档索引

更新时间：2026-07-01

本目录用于沉淀 InsightPilot 的产品、技术、数据和测试文档。当前文档已按项目真实实现状态完成一次校准，后续新增功能时请优先同步这里，避免出现“代码已变、文档还停留在旧版本”的情况。

## 1. 建议阅读顺序

1. `insightpilot_version_status_and_roadmap.md`
2. `insightpilot_prd.md`
3. `insightpilot_technical_design.md`
4. `insightpilot_er_design.md`
5. `testing/` 下的联调与验证记录

## 2. 核心文档说明

- `insightpilot_version_status_and_roadmap.md`
  当前版本真实状态、已完成能力、未完成边界，以及下一版本的迭代路线。
- `insightpilot_prd.md`
  产品目标、用户角色、核心闭环、验收口径与阶段目标。
- `insightpilot_technical_design.md`
  当前技术架构、模块分层、数据库策略、RAG 与 Agent 设计、异步任务链路。
- `insightpilot_er_design.md`
  数据表设计、字段说明、表间关系约定与演示数据覆盖原则。

## 3. 当前版本事实基线

- 当前项目已经完成 V1 骨架和主演示链路，不再是纯占位工程。
- 前端已完成 V2 工作台改造，核心页面包括：
  - 登录页
  - 经营驾驶舱
  - 风险中心
  - AI 审批台
  - 销售任务
  - 经营报告
  - Agent Trace
  - RAG 评估
- 数据库基线已重建：
  - `backend/scripts/init_schema.sql` 已补齐中文表注释和字段注释
  - `backend/scripts/seed_demo_data.sql` 已替换为更真实的模拟数据
  - `backend/alembic/versions/20260701_0001_init_schema_with_comments.py` 已作为首个 Alembic baseline revision
- 数据库设计继续坚持两条原则：
  - 不设置外键
  - 仅通过同名字段做隐式关联
- 风险扫描当前已经通过真实 `LangGraph` 风险扫描图跑通“规则识别 -> RAG 增强 -> LLM 建议 -> 人工审批草稿 -> Agent Trace 落库”主链路。
- `langgraph` 当前已完成风险扫描图和经营日报图落地。
- 销售任务当前已具备最小执行闭环：可开始、完成、取消，完成时会自动回写 CRM 跟进记录。

## 4. 当前阶段后续候选

风险扫描图已经落地后，当前阶段更适合继续评估这些候选方向：

- 销售任务执行闭环补强
- CSV 导入能力
- RQ / Redis / Milvus 全链路回归验证

后续继续演进时，建议保持这些约束：

- 保留现有接口返回结构
- 保留 `agent_run`、`agent_step`、`rag_retrieval_trace` 等落库行为
- 保留前端 Agent Trace 页面当前依赖的节点展示方式
- 避免重新回到 Worker 大函数堆叠模式

## 5. 文档维护约定

- 任何影响用户理解的变更，都要同步更新 PRD 或版本路线图。
- 任何影响架构认知的变更，都要同步更新技术方案文档。
- 任何影响表结构、字段含义、初始化方式的变更，都要同步更新 ER 文档或初始化说明。
- 如果实现和文档不一致，以代码为准，但要尽快把文档补齐。
