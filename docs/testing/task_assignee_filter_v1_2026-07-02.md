# 任务负责人筛选增强 V1 测试记录

## 测试日期

- 2026-07-02

## 功能范围

- 任务负责人轻量列表接口支持关键词筛选
- 负责人候选范围收口为“在职且具备可执行角色的用户”
- 任务页批量分配负责人下拉支持按关键词过滤

## 设计说明

- 当前项目还没有组织架构表或真正的团队归属模型
- 因此这一版不做伪“团队成员树”过滤
- 当前版本的合理收口方式是：
  - 只返回在职用户
  - 只返回具备 `owner / manager / salesperson` 角色的候选人
  - 支持按 `user_id / username / real_name` 关键词过滤

## 测试方式

### 1. 真实接口筛选烟测

执行方式：

- 使用 `FastAPI TestClient`
- 用 `manager / Manager@123456` 登录
- 调用 `/api/tasks/assignees`
- 校验返回列表非空，且每个用户都具备可分配角色
- 再用首条记录的 `user_id` 作为关键词，校验筛选结果能够命中该负责人

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

all_result = client.get('/api/tasks/assignees', headers=headers)
all_users = all_result.json()['data']
first_user = all_users[0]
allowed = {'owner', 'manager', 'salesperson'}

assert all_users
assert all(set(user.get('role_codes', [])) & allowed for user in all_users)

filtered = client.get(f"/api/tasks/assignees?keyword={first_user['user_id']}", headers=headers)
filtered_users = filtered.json()['data']
assert any(user['user_id'] == first_user['user_id'] for user in filtered_users)

print(len(all_users))
print(first_user)
print(len(filtered_users))
'@ | python
```

结果：

- 通过
- 全量负责人列表返回 5 条
- 首条负责人可正常被关键词筛选命中
- 接口返回中已包含：
  - `user_id`
  - `username`
  - `real_name`
  - `role_codes`
  - `role_names`

说明：

- PowerShell 终端里中文姓名和角色名仍有编码乱码
- 但结构化字段和筛选行为正确，不影响前端下拉联动

### 2. 前端生产构建验证

执行命令：

```powershell
cd frontend
npm.cmd run build:verify
```

结果：

- 通过
- `/tasks` 页面构建通过
- 新增的负责人筛选输入框、角色展示和关键词请求没有引入 TypeScript 或 Next.js 构建错误

构建输出摘录：

```text
└ ○ /tasks                               5.63 kB         116 kB
```

## 结论

- 本轮“任务负责人筛选增强”已完成并验证通过
- 当前版本已经把负责人分配能力收口到更真实的可执行范围：
  - 只看在职负责人
  - 只看适合作为任务执行人的角色用户
  - 支持关键词筛选

## 备注

- 由于当前还没有组织架构模型，这一版不包含严格的团队层级过滤
- 如果后续补齐组织树、部门、直属关系或团队成员表，这里可以自然升级为真正的“仅本团队可分配”
