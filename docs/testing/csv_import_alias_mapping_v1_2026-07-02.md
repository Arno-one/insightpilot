# CSV 字段别名识别与轻量映射测试记录

## 测试日期

- 2026-07-02

## 功能范围

- 字段别名自动识别
- 手动补映射
- 映射后前端标准化 CSV
- 继续复用现有导入接口

## 测试方式

### 1. 前端构建检查

执行命令：

```powershell
npm.cmd run build:verify
```

结果：

- 通过
- `/imports` 页面构建成功
- 本次映射逻辑未引入 TypeScript 报错
- 构建产物中 `/imports` 页面大小为 `10.1 kB`

### 2. 轻量映射烟测

执行方式：

- 使用 Node 脚本模拟当前前端别名识别与补映射逻辑
- 构造一组“部分可自动识别、部分需要手动补映射”的原始表头

原始表头样例：

- `customer_no`
- `name`
- `owner_id`
- `stage`
- `intent`
- `level`
- `trade`
- `city`
- `custom_follow_time`
- `memo`

自动识别结果：

- 自动映射成功：
  - `customer_no -> customer_id`
  - `name -> customer_name`
  - `owner_id -> owner_user_id`
  - `stage -> lifecycle_stage`
  - `intent -> intent_level`
  - `level -> customer_level`
  - `trade -> industry`
  - `city -> region`
- 自动识别后仍缺失：
  - `next_follow_up_at`
  - `remark`
- 自动识别后仍未映射原始表头：
  - `custom_follow_time`
  - `memo`

手动补映射后结果：

- `custom_follow_time -> next_follow_up_at`
- `memo -> remark`
- 补映射后：
  - `missingRequiredFields = []`
  - `unmappedSourceHeaders = []`

### 3. 结论

- 本轮“字段别名识别/轻量映射”逻辑测试通过
- 当前实现已经满足 V1 收口目标：
  - 标准模板可直接导入
  - 常见非标准表头可自动识别
  - 剩余字段可手动补映射
  - 映射后仍复用现有导入接口

## 备注

- 本轮未单独执行浏览器自动化点击测试
- 但已完成：
  - 前端构建验证
  - 映射逻辑烟测
  - 页面代码接入检查
