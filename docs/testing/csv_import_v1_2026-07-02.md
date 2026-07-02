# CSV 导入 V1 测试记录

## 测试日期

- 2026-07-02

## 功能范围

- CRM 统一导入页 `/imports`
- 客户模板下载 `GET /api/crm/import/templates/{entity}.csv`
- 客户导入 `POST /api/crm/import/customer`
- 商机导入 `POST /api/crm/import/deal`
- 跟进记录导入 `POST /api/crm/import/follow_up`
- 复用现有 CRM 读取权限
- 导入后回查客户详情聚合链路

## 测试方式

### 1. 后端语法检查

执行命令：

```powershell
python -m compileall backend/app
python -m compileall backend/app/modules/crm
```

结果：

- 通过

### 2. 前端构建检查

执行命令：

```powershell
npm.cmd run build:verify
```

结果：

- 通过
- Next.js 构建产物中已包含 `/imports` 页面

### 3. 主链路烟测

测试账号：

- `manager / Manager@123456`

测试步骤：

1. 登录获取 token
2. 下载客户导入模板
3. 导入 1 条新客户
4. 再次导入同一客户，验证“只新增不覆盖”
5. 导入 1 条新商机
6. 导入 1 条新跟进记录
7. 回查客户详情接口，验证跟进已可见且客户主表已同步更新
8. 清理本次烟测写入的数据

结果：

- 登录成功，状态码 `200`
- 模板下载成功，状态码 `200`
- 客户导入成功：`total=1 success=1 failed=0`
- 重复客户导入拦截成功：`total=1 success=0 failed=1`
- 商机导入成功：`total=1 success=1 failed=0`
- 跟进导入成功：`total=1 success=1 failed=0`
- 客户详情回查成功，状态码 `200`
- 回查结果确认：
  - 新导入的 `follow_up_id` 已出现在客户详情 `follow_ups`
  - `customer.last_sentiment` 已更新为 `positive`
  - `customer.next_follow_up_at` 已更新为导入值

### 4. 权限范围烟测

测试账号：

- `sales01 / Sales@123456`

测试步骤：

1. 使用销售账号登录
2. 尝试导入一条 `owner_user_id = u_sales_002` 的客户

结果：

- 登录成功，状态码 `200`
- 导入接口返回 `200`
- 行级校验生效：`failed_count=1 success_count=0`
- 已确认命中“销售员只能导入自己 owner 的客户”范围限制

## 测试过程中发现并修复的问题

### 问题描述

- 在“导入成功后立刻回查客户详情”时，商机查询 SQL 的 `updated_at` 字段未带表别名。
- 因为联表了 `sys_user owner`，MySQL 返回了歧义列错误：

```text
Column 'updated_at' in field list is ambiguous
```

### 修复方式

- 已在 `backend/app/modules/crm/router.py` 中把商机详情查询字段改为显式别名：
  - `d.updated_at`

### 修复后复测

- 主链路烟测重新执行后通过

## 结论

- 本轮 CSV 导入 V1 功能测试通过
- 已满足当前约束：
  - 三类导入同轮完成
  - 最小必需字段集
  - 只新增不覆盖
  - 复用现有 CRM 读取权限
  - 每个功能完成后执行测试并沉淀测试文档
