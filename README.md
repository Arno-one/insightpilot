# InsightPilot

InsightPilot 是面向中小企业的 AI 企业运营参谋系统。V1 聚焦销售客户流失风险分析，通过 CRM 数据、规则引擎、LangGraph Agent、RAG 知识库、人工审批和销售任务形成闭环。

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic、MySQL
- Agent：LangGraph
- RAG：Milvus、DashScope Embedding、DeepSeek、CrossEncoder
- 缓存与队列：Redis、RQ
- 前端：Next.js、React

## 本地目录

```text
backend/   FastAPI 后端
frontend/  Next.js 前端
docs/      项目文档
```

## 初始化顺序

```text
1. 配置 backend/.env
2. 执行 backend/scripts/init_schema.sql
3. 执行 backend/scripts/seed_demo_data.sql
4. 启动后端和 RQ worker
5. 启动前端
```

## 演示账号

```text
admin / Admin@123456
owner / Owner@123456
manager / Manager@123456
sales01 / Sales@123456
sales02 / Sales@123456
sales03 / Sales@123456
```
