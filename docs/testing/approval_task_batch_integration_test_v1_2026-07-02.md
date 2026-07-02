# 审批与任务批量操作真实数据库集成测试 V1 记录

## 测试日期

- 2026-07-02

## 测试目标

- 为“审批与任务执行闭环增强”模块补一条可重复执行的真实数据库集成测试
- 覆盖以下关键链路：
  - 批量审批
  - 批量分配负责人
  - 批量更新任务状态
  - 留痕事件写入
  - 测试数据自动清理

## 新增测试文件

- [backend/tests/test_approval_task_batch_integration.py](/D:/insightpilot/backend/tests/test_approval_task_batch_integration.py)

## 测试方式

### 1. 后端编译检查

执行命令：

```powershell
python -m compileall backend/app backend/tests
```

结果：

- 通过
- 新增集成测试文件编译通过
- 本轮补充的任务负责人筛选后端代码也编译通过

### 2. 真实数据库集成测试

执行命令：

```powershell
cd backend
$env:PYTHONPATH='D:\insightpilot\backend'
python -m pytest tests/test_approval_task_batch_integration.py -q
```

结果：

- 通过
- `1 passed in 2.70s`

## 集成测试覆盖内容

该测试会在真实 MySQL 中自动完成以下步骤：

1. 使用 `manager / Manager@123456` 登录获取真实权限上下文
2. 自动补齐 `approval_task_event` 表
3. 插入临时客户与两条临时审批记录
4. 调用 `POST /api/approvals/batch-review` 批量通过审批
5. 校验是否生成两条正式任务
6. 调用 `PATCH /api/tasks/batch/assignee` 批量改派负责人
7. 调用 `PATCH /api/tasks/batch/status` 批量开始执行
8. 直接查询 MySQL 校验：
   - 任务负责人已变更
   - 任务状态已变更
   - 留痕表中已有 `approval_approved / task_created / task_reassigned / task_in_progress`
9. 自动清理临时客户、审批、任务、跟进记录与留痕记录

## 关键发现

- 首次执行时发现本地 MySQL 尚未落上 `approval_task_event` 表
- 为了让真实数据库回归在当前仓库中可重复执行，测试文件增加了幂等建表保护
- 这说明当前业务代码已经依赖留痕表，后续在新环境初始化时应确保对应迁移已执行

## 结论

- 本轮“真实数据库场景集成测试”已完成并通过
- 到这里，这个版本里“审批与任务执行闭环增强”模块的收口能力已经补齐：
  - 页面可批量操作
  - 页面可回看失败明细
  - 负责人分配有更真实的筛选边界
  - 后端有真实数据库回归基线

## 备注

- 测试依赖本地 MySQL 中存在可登录的 `manager` 账号和基础 RBAC 演示数据
- 测试会自动创建并清理临时业务数据，不会长期污染现有演示数据
