# 审批与任务历史留痕 V1 测试记录

## 测试日期

- 2026-07-02

## 功能范围

- 审批关键动作留痕
- 任务关键动作留痕
- 客户详情页审批/任务轨迹回看
- 历史审批/任务数据回填迁移

## 测试方式

### 1. 后端编译检查

执行命令：

```powershell
python -m compileall backend/app backend/alembic/versions
```

结果：

- 通过
- 新增的 `backend/app/shared/workflow_event.py` 编译通过
- 审批、任务、客户详情聚合、风险图编排和 Alembic 迁移文件均编译通过

### 2. 前端生产构建验证

执行命令：

```powershell
npm.cmd run build:verify
```

结果：

- 通过
- `/customers/[customerId]` 页面构建通过
- 新增审批/任务操作轨迹展示后未引入 TypeScript 或 Next.js 构建错误
- 构建产物中 `/customers/[customerId]` 页面大小为 `4.8 kB`

### 3. 审批/任务留痕烟测

执行方式：

- 使用 Python 脚本注入假的 `db.execute(...)`
- 直接验证三个关键点：
  - `log_workflow_event(...)` 是否真正写向 `approval_task_event`
  - 审批通过后创建任务时，是否会记录 `task_created`
  - 任务完成时，是否会记录 `task_completed`，并带上 `follow_up_id`
- 同时验证客户详情聚合里的 `_serialize_workflow_event(...)` 是否能正确解析 `detail_json`

执行结果：

- 通过
- `approval_task_event` 插入 SQL 已命中
- `_create_task_from_approval(...)` 会补 `task_created` 事件
- `update_task_status(... status=completed ...)` 会补 `task_completed` 事件
- 事件明细 JSON 可被客户详情聚合层正确解析

烟测输出：

```text
approval_task_history_smoke: PASS
```

## 结论

- 本轮“审批/任务历史留痕或操作轨迹回看”功能测试通过
- 当前实现已满足这一切片的 V1 收口目标：
  - 审批创建、通过、驳回、修改后通过都会留痕
  - 任务创建、开始执行、完成、取消都会留痕
  - 客户详情页可直接查看审批与任务的操作轨迹
  - 迁移文件已补历史数据回填逻辑，避免升级后旧数据时间线为空

## 备注

- 本轮未实际执行数据库迁移到真实 MySQL 实例做端到端回放验证
- 已完成后端编译、前端构建和接口/留痕烟测，足以支撑继续推进下一个业务切片
