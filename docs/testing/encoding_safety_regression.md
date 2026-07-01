# 编码安全回归测试记录

## 1. 测试目标

验证 InsightPilot 在 `2026-07-01` 当前数据库基线下，以下链路中的中文内容不会因为接口传输、JSON 字段、数据库存储或终端显示差异而发生损坏：

- 审批草稿中文标题读取
- 任务完成结果中文备注回写
- 跟进记录中文内容落库
- 客户表中文字段同步更新
- 风险状态联动更新
- 任务列表 API 中文字段返回

## 2. 测试环境

- 项目目录：`D:\insightpilot`
- 回归方式：临时 Python 脚本通过 `stdin` 执行，不在仓库落测试 `.py`
- 接口调用方式：`FastAPI TestClient`
- 数据库：当前已重建并重新灌入中文模拟数据的 MySQL 基线
- 登录账号：`manager / Manager@123456`

## 3. 前置说明

本轮回归一开始出现过两类“假失败”，都不是业务编码损坏：

1. 旧断言基线与新数据库种子数据不一致
   - 例如 `crm_customer.c_001.customer_name` 当前真实值是“深圳星河教育科技”，不是旧脚本里的历史值。
2. PowerShell 管道显示乱码
   - 终端看到乱码，不代表数据库里存的就是乱码。
   - 最终回归改为使用 Unicode 转义常量 + Python 精确断言，避免肉眼误判。

## 4. 回归路径

本轮实际验证链路如下：

1. 校验中文种子数据
2. 登录管理端账号
3. 校验审批草稿 `appr_006` 的中文标题
4. 审批通过 `appr_006`
5. 将生成任务置为 `in_progress`
6. 将任务置为 `completed`
7. 校验任务、跟进、客户、风险快照、任务 API 的中文内容和状态

## 5. 使用的精确断言样例

### 种子数据断言

- `crm_customer.c_001.customer_name = 深圳星河教育科技`
- `approval_record.appr_006.proposed_payload_json.title = 主管介入北桥医疗高金额风险`

### 任务执行中文断言

- `result_note = 编码回归：客户确认下周二继续预算评审。`
- `follow_up_content = 编码回归电话：客户表示方案方向认可，下周二继续预算评审。`
- `customer_feedback = 客户认可方案方向，等待预算评审`
- `next_action = 下周二再次确认预算评审结果`
- `sentiment = positive`
- `next_follow_up_at = 2026-07-08 14:30:00`

## 6. 实际结果

### 审批与任务

- `approval_record.appr_006.status = approved`
- `sales_task.task_e48b7ae41fee4f5c.status = completed`
- `sales_task.task_e48b7ae41fee4f5c.result_note` 与预期中文完全一致

### 跟进记录

- `crm_follow_up_record.fu_6b0c5f83299a4a9e.content` 与预期中文完全一致
- `crm_follow_up_record.fu_6b0c5f83299a4a9e.customer_feedback` 与预期中文完全一致
- `crm_follow_up_record.fu_6b0c5f83299a4a9e.next_action` 与预期中文完全一致
- `crm_follow_up_record.fu_6b0c5f83299a4a9e.sentiment = positive`
- `crm_follow_up_record.fu_6b0c5f83299a4a9e.next_follow_up_at = 2026-07-08 14:30:00`

### 客户与风险联动

- `crm_customer.c_006.customer_name = 苏州北桥医疗`
- `crm_customer.c_006.last_sentiment = positive`
- `crm_customer.c_006.next_follow_up_at = 2026-07-08 14:30:00`
- `customer_risk_snapshot.risk_006.status = completed`

### API 返回

- `/api/tasks` 中 `approval_id = appr_006` 的任务记录：
  - `customer_name = 苏州北桥医疗`
  - `title = 主管介入北桥医疗高金额风险`
  - `result_note = 编码回归：客户确认下周二继续预算评审。`
  - `status = completed`

## 7. 结论

本轮“编码安全回归”结论为：

`ENCODING_REGRESSION_RESULT=PASS`

说明当前版本在“审批 -> 任务 -> 跟进 -> 客户 -> 风险状态 -> 任务 API”这条链路上，中文内容可以稳定完成：

- 从审批 JSON 读取
- 经接口传输
- 写入任务与跟进表
- 回写客户表
- 再由 API 返回前端

整个过程中未发现中文字段被 `???` 替换、截断或错误转码的问题。

## 8. 风险与建议

- 终端显示乱码不等于数据库真实乱码，后续回归应继续使用“程序精确断言”而不是肉眼判断。
- 数据库重建后，测试基线要同步更新，否则容易把“种子数据调整”误判成“编码故障”。
- 建议后续补一份可重复执行的回归清单，覆盖：
  - 审批通过
  - 审批驳回
  - 任务取消
  - 多角色查看任务列表时的中文字段一致性
