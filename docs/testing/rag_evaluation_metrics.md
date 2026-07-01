# RAG 检索评估指标测试记录

## 测试目标

验证 InsightPilot RAG 模块具备初版可量化评估能力：

- 使用 QA 数据集作为评估集。
- 每条 QA 的 `doc_id + section_id` 作为期望命中来源。
- 计算 `Recall@K`、`MRR`、`NDCG`。
- 后端提供 `POST /api/rag/evaluate`。
- 前端新增 `/rag-evaluation` 页面展示指标和逐条 case 结果。

## 测试环境

- 项目路径：`D:\insightpilot`
- 测试向量库：Milvus Lite 本地文件 `backend/tests/rag_test_milvus.db`
- 测试 Embedding：关闭真实 DashScope 调用，使用确定性向量降级。
- 评估数据：`docs/insightpilot_rag_docs/InsightPilot全量QA数据集.jsonl.md`

## 服务级测试

执行命令：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'
Remove-Item Env:MILVUS_URI -ErrorAction SilentlyContinue
$env:USE_REAL_EMBEDDING='false'

@'
from app.core.config import settings
settings.milvus_uri = 'D:/insightpilot/backend/tests/rag_test_milvus.db'
settings.use_real_embedding = False

from app.modules.rag.evaluation_service import evaluate_rag_retrieval

result = evaluate_rag_retrieval('demo_tenant', 'u_owner_001', top_k=5, limit=5, enable_rerank=True)
print({k: result[k] for k in ['top_k', 'case_count', 'hit_count', 'recall_at_k', 'mrr', 'ndcg', 'duration_ms']})
for item in result['details']:
    print(item['case_id'], item['hit'], item['rank'], item['expected_doc_id'], item['expected_section_id'])
'@ | python
```

测试结果：

- `top_k=5`
- `case_count=5`
- `hit_count=5`
- `recall_at_k=1.0`
- `mrr=0.9`
- `ndcg=0.9262`

逐条 case：

- `qa_obj_001_001`：命中，rank=1
- `qa_obj_001_002`：命中，rank=1
- `qa_obj_001_003`：命中，rank=1
- `qa_obj_001_004`：命中，rank=2
- `qa_obj_001_005`：命中，rank=1

## 接口级测试

执行命令：

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
login = client.post('/api/auth/login', json={'username': 'owner', 'password': 'Owner@123456'})
token = login.json()['data']['token']
resp = client.post(
    '/api/rag/evaluate',
    json={'top_k': 5, 'limit': 5, 'enable_rerank': True},
    headers={'Authorization': f'Bearer {token}'},
)
print(resp.status_code, resp.json()['code'], resp.json()['total'])
print({k: resp.json()['data'][k] for k in ['case_count', 'hit_count', 'recall_at_k', 'mrr', 'ndcg']})
'@ | python
```

测试结果：

- HTTP 状态码：200
- 业务码：200
- `total=5`
- `case_count=5`
- `hit_count=5`
- `recall_at_k=1.0`
- `mrr=0.9`
- `ndcg=0.9262`

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
- 新增 `/rag-evaluation` 页面构建成功。
- 构建无 CSS 兼容性警告。

## 结论

RAG 模块已具备初版检索质量评估闭环。后续可以在此基础上扩展：

- 增加按文档类型分组的 Recall/MRR/NDCG。
- 增加评估结果落库。
- 增加 CrossEncoder rerank 前后对比。
- 增加 TopK、Query Rewrite、chunk_size 参数对比实验。
