# InsightPilot

InsightPilot 是一个面向中小企业销售经营场景的 AI Enterprise Agent Platform。项目以 CRM 数据为底座，把客户风险识别、RAG 证据检索、自然语言问数、Agent 执行、人工审批、任务闭环、通知投递和运行审计串成一套可落地的经营辅助系统。

## 核心能力

- 经营驾驶舱：汇总客户风险、审批、任务、日报和系统健康状态。
- 客户工作台：围绕客户恢复跟进记录、风险摘要和 Agent 对话上下文。
- 统一 Agent 对话：从一个入口路由风险分析、经营问数、执行建议等 Agent 能力。
- 智能问数 NL2SQL：用中文生成只读 SQL，查询 CRM / 风险 / 审批 / 任务数据，并保留审计链路。
- RAG 知识库：接入文档切分、向量检索、重排、引用证据和评测指标。
- 人工审批与销售任务：AI 建议先进入审批，再转为可执行任务。
- 通知中心：记录通知投递状态，支持失败追踪和重试。
- Agent 追踪：展示 Agent Run、Step、RAG Trace、Action Chain、慢操作 TopN 和恢复事件。
- 系统管理：维护角色权限、用户角色、发布门禁、部署就绪、备份恢复和企业硬化信息。

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic、MySQL。
- Agent：LangGraph、自研 MCP Gateway、内部工具注册表。
- RAG：Milvus、DashScope Embedding、DeepSeek、Sentence Transformers。
- 异步与调度：Redis、RQ、APScheduler。
- 前端：Next.js、React、TypeScript。

## 目录结构

```text
backend/                 FastAPI 后端、Alembic 迁移、Worker、初始化脚本
frontend/                Next.js 前端
docs/                    产品、架构、验收、测试和迭代文档
requirements.txt         根目录 Python 依赖清单
.env.examplate           根目录环境变量示例
```

## 环境要求

- Python 3.10+。
- Node.js 20+。
- MySQL 8.x。
- Redis 6+。
- 可选：Milvus，用于真实向量检索；不开启真实 Embedding 时可先用降级模式跑通基础流程。

## 后端启动

```powershell
cd D:\insightpilot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

复制并修改环境变量：

```powershell
Copy-Item .env.examplate .env
```

初始化数据库：

```powershell
mysql -h localhost -P 3306 -u root -p insightpilot < backend/scripts/init_schema.sql
mysql -h localhost -P 3306 -u root -p insightpilot < backend/scripts/seed_demo_data.sql
```

启动 API：

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.main:app --host 0.0.0.0 --port 8088 --reload
```

启动 RQ Worker：

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python worker.py
```

启动定时任务进程：

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python scheduler_worker.py
```

## 前端启动

```powershell
cd D:\insightpilot\frontend
npm install
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

默认前端会访问 `http://localhost:8088`。如需修改后端地址，在 `frontend/.env.local` 中配置：

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8088
```

## 常用验证

后端语法检查：

```powershell
cd D:\insightpilot
python -m compileall backend/app -q
```

后端测试：

```powershell
cd D:\insightpilot\backend
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests -q
```

前端构建验证：

```powershell
cd D:\insightpilot\frontend
npm.cmd run build:verify
```

部署就绪检查：

```powershell
cd D:\insightpilot\backend
$env:PYTHONPATH = (Get-Location).Path
python scripts/verify_deployment_readiness.py
```

## 演示账号

```text
admin   / Admin@123456
owner   / Owner@123456
manager / Manager@123456
sales01 / Sales@123456
sales02 / Sales@123456
sales03 / Sales@123456
```

## 环境变量说明

- MySQL：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。
- 只读问数账号：`MYSQL_READONLY_USER`、`MYSQL_READONLY_PASSWORD`，生产环境建议单独配置。
- Redis / RQ：`REDIS_HOST`、`REDIS_PORT`、`REDIS_DB`、`REDIS_PASSWORD`。
- 鉴权：`AUTH_SECRET_KEY`、`AUTH_TOKEN_EXPIRE_MINUTES`、`AUTH_PBKDF2_ITERATIONS`。
- LLM / NL2SQL：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`NL2SQL_MODEL`。
- RAG：`DASHSCOPE_API_KEY`、`ALIYUN_API_KEY`、`MILVUS_URI`、`MILVUS_DB_NAME`、`RAG_*`。
- 邮件：`SMTP_HOST`、`SMTP_PORT`、`SENDER_EMAIL`、`SMTP_AUTH_CODE`、`SMTP_*`。
- 前端：`NEXT_PUBLIC_API_BASE_URL`、`NEXT_DIST_DIR`。

## 安全提醒

- 不要提交真实 `.env`、数据库密码、SMTP 授权码和模型 API Key。
- 生产环境必须替换 `AUTH_SECRET_KEY`，并为 NL2SQL 配置只读数据库账号。
- 执行 AI 动作前应保持人工审批链路开启，避免自动化动作直接影响真实客户。
