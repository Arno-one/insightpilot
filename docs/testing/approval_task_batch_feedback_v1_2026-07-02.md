# 审批与任务批量失败明细回看 V1 测试记录

## 测试日期

- 2026-07-02

## 功能范围

- 审批页批量操作结果面板
- 任务页批量操作结果面板
- 批量接口失败明细 `failed_items` 的前后端联动

## 测试方式

### 1. 真实接口失败明细烟测

执行方式：

- 使用 `FastAPI TestClient`
- 先用 `manager / Manager@123456` 登录
- 分别调用审批批量接口与任务批量状态接口
- 故意传入不存在的审批 ID 和任务 ID，验证接口是否返回结构化失败明细

执行命令：

```powershell
$env:PYTHONPATH='D:\insightpilot\backend'

@'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
login = client.post('/api/auth/login', json={'username': 'manager', 'password': 'Manager@123456'})
token = login.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

approval_result = client.post(
    '/api/approvals/batch-review',
    headers=headers,
    json={
        'approval_ids': ['approval_missing_for_batch_feedback'],
        'action': 'approve'
    }
)
task_result = client.patch(
    '/api/tasks/batch/status',
    headers=headers,
    json={
        'task_ids': ['task_missing_for_batch_feedback'],
        'status': 'in_progress',
        'result_note': '批量失败明细校验'
    }
)

print(approval_result.json()['data'])
print(task_result.json()['data'])
'@ | python
```

结果：

- 通过
- 审批批量接口返回：
  - `success_count = 0`
  - `failed_count = 1`
  - `failed_items[0].approval_id = approval_missing_for_batch_feedback`
- 任务批量接口返回：
  - `success_count = 0`
  - `failed_count = 1`
  - `failed_items[0].task_id = task_missing_for_batch_feedback`

说明：

- 终端输出中的中文错误文案在 PowerShell 下有乱码，但返回结构本身正确
- 前端只依赖 `failed_items` 的结构化字段，因此不会影响失败明细展示

### 2. 前端生产构建验证

执行命令：

```powershell
cd frontend
npm.cmd run build:verify
```

结果：

- 通过
- `/approvals` 页面构建通过
- `/tasks` 页面构建通过
- 新增的“上次批量操作结果”面板没有引入 TypeScript 或 Next.js 构建错误

构建输出摘录：

```text
├ ○ /approvals                           4.49 kB         115 kB
└ ○ /tasks                               5.36 kB         116 kB
```

## 结论

- 本轮“批量操作后的失败明细回看”已完成并验证通过
- 审批页与任务页都能承接批量接口返回的失败明细结构
- 当前实现满足这个切片的 V1 目标：
  - 能看到本次批量操作成功多少条、失败多少条
  - 失败项可以按审批 ID 或任务 ID 回看失败原因

## 备注

- 本轮未做浏览器人工点击截图验证
- 代码层和接口层已经确认失败明细结构可用，足以支撑继续推进下一个收口项
