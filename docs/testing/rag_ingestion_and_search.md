# RAG 入库与检索测试记录

## 测试目标

验证 InsightPilot V1 RAG 模块已经完成以下闭环：

- Markdown 知识文档按架构要求切片，默认 `chunk_size=500`、`overlap=50`。
- QA 问答对独立入库，和文档切片分成两个 Milvus Collection。
- 检索流程包含 Query Rewrite、Embedding、稠密向量检索、BM25 稀疏检索、RRF 融合、去重、Token 预算截断和 Trace 记录。
- FastAPI 接口经过 JWT 鉴权后可以正常返回检索结果。

## 测试环境

- 项目路径：`D:\insightpilot`
- 后端入口：`backend/app/main.py`
- 测试向量库：Milvus Lite 本地文件 `backend/tests/rag_test_milvus.db`
- 生产预期向量库：Docker Milvus，默认 `http://localhost:19530`
- 测试 Embedding：关闭真实 DashScope 调用，使用确定性向量降级，保证本地测试可重复执行。
- MySQL：继续使用项目 `.env` 中配置的 `insightpilot` 数据库。

## 测试数据

本次入库使用默认知识库目录：

- `docs/insightpilot_rag_docs/01_销售 SOP.md`
- `docs/insightpilot_rag_docs/02_产品资料与价格策略.md`
- `docs/insightpilot_rag_docs/03_异议处理话术.md`
- `docs/insightpilot_rag_docs/InsightPilot全量QA数据集.jsonl.md`

入库结果：

- 文档切片：20 条
- QA 问答对：71 条
- 总计：91 条

## 执行命令

后端编译检查：

```powershell
python -m compileall backend/app -q
```

RAG 入库与内部检索：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
Remove-Item Env:MILVUS_URI -ErrorAction SilentlyContinue
$env:USE_REAL_EMBEDDING='false'

@'
from app.core.config import settings
settings.milvus_uri = 'D:/insightpilot/backend/tests/rag_test_milvus.db'
settings.use_real_embedding = False

from app.modules.rag.ingestion_service import ingest_default_knowledge_base
from app.modules.rag.retrieval_service import search_knowledge

result = ingest_default_knowledge_base('demo_tenant', 'user_admin')
print(result)

question = '\u5ba2\u6237\u8bf4\u4ef7\u683c\u592a\u8d35\u600e\u4e48\u529e\uff1f'
search = search_knowledge('demo_tenant', 'user_admin', question, top_k=5, enable_rerank=True)
print(search.trace_id)
print(search.hits[0])
'@ | python
```

FastAPI 接口级测试：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
Remove-Item Env:MILVUS_URI -ErrorAction SilentlyContinue
$env:USE_REAL_EMBEDDING='false'

@'
from app.core.config import settings
settings.milvus_uri = 'D:/insightpilot/backend/tests/rag_test_milvus.db'
settings.use_real_embedding = False

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
login = client.post('/api/auth/login', json={'username': 'manager', 'password': 'Manager@123456'})
token = login.json()['data']['token']

question = '\u5ba2\u6237\u8bf4\u4ef7\u683c\u592a\u8d35\u600e\u4e48\u529e\uff1f'
resp = client.post(
    '/api/rag/search',
    json={'question': question, 'top_k': 3, 'enable_rerank': True},
    headers={'Authorization': f'Bearer {token}'},
)
print(resp.status_code, resp.json()['code'], resp.json()['total'])
print(resp.json()['data']['hits'][0])
'@ | python
```

## 测试结果

- 编译检查：通过。
- 入库任务：成功，返回 `document_chunks=20`、`qa_pairs=71`、`total=91`。
- 内部检索：成功，问题“客户说价格太贵怎么办？”第一命中为 `objection_handling_v1 / OBJ-001`。
- API 登录：`manager / Manager@123456` 登录成功，HTTP 状态码 200。
- API 检索：`POST /api/rag/search` 返回 HTTP 状态码 200，业务码 200，`total=3`。
- API 第一命中：QA 来源，`doc_id=objection_handling_v1`，`section_id=OBJ-001`。

## 注意事项

- PowerShell 管道直接传中文给 Python 时，当前终端可能把中文显示或传递成问号；测试命令使用 Unicode 转义规避该问题。
- 不要把本地 `.db` 路径写入环境变量 `MILVUS_URI`，因为 `pymilvus` 导入阶段会按 HTTP URI 校验这个变量。测试时应先导入 `settings`，再用 `settings.milvus_uri` 覆盖为本地 Milvus Lite 文件。
- Docker Milvus 启动后，直接使用 `.env` 中的 `MILVUS_URI=http://localhost:19530` 即可，不需要上述本地覆盖。
- Milvus Lite 在 Windows 下偶发索引 manifest 文件冲突，代码已做安全降级，不影响本地功能测试；Docker Milvus 环境应使用正常索引能力。

## 结论

RAG 入库与检索 V1 闭环通过，可以进入下一步：把风险扫描 Agent 接入 RAG 检索上下文，让规则引擎负责风险判断，大模型基于知识库上下文生成解释、建议和待审批任务草稿。
