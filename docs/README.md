# InsightPilot 文档索引

当前目录用于沉淀项目设计文档。完整交付文档最初生成在 Codex outputs 目录，后续可以复制到本目录继续维护。

建议纳入的文档：

- `insightpilot_prd.md`：产品需求文档。
- `insightpilot_technical_design.md`：技术方案文档。
- `insightpilot_er_design.md`：完整 ER 设计。
- `RAG高级架构流程总结.md`：RAG 从切片到评估的完整流程。

V1 开发顺序：

1. 后端核心配置、数据库、Redis、RQ。
2. 初始化 SQL 和模拟数据。
3. Auth + JWT + RBAC。
4. CRM 查询和风险规则引擎。
5. RAG 入库和检索。
6. LangGraph 风险分析图。
7. 审批、销售任务和经营日报。
8. Next.js SaaS 工作台接入真实接口。
