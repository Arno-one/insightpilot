# 前端真实 API 工作台测试记录

## 测试目标

验证 InsightPilot 前端从静态骨架升级为真实可用工作台：

- 登录页接入 `POST /api/auth/login`。
- JWT token 和当前用户信息保存到浏览器本地存储。
- `AppShell` 根据 RBAC 权限过滤菜单，并支持退出登录。
- 驾驶舱读取风险、审批、任务、报告真实数据。
- 风险中心、审批台、销售任务、经营报告、Agent Trace 页面均接入后端接口。
- 前端项目通过 Next.js 生产构建。

## 涉及页面

- `/login`
- `/dashboard`
- `/risks`
- `/approvals`
- `/tasks`
- `/reports`
- `/agent-trace`

## API 配置

默认 API 地址：

```text
http://localhost:8088
```

如需修改，前端可配置：

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8088
```

## 执行命令

PowerShell 默认执行策略会拦截 `npm.ps1`，因此本次使用 `npm.cmd`：

```powershell
npm.cmd run build
```

## 测试结果

构建结果：

- Next.js 版本：15.5.19
- 编译：通过
- TypeScript 类型检查：通过
- 静态页面生成：通过，生成 11 个页面

核心页面构建结果：

- `/login`
- `/dashboard`
- `/risks`
- `/approvals`
- `/tasks`
- `/reports`
- `/agent-trace`

## 功能说明

- 登录页支持老板、销售主管、销售员三个演示账号快速填充。
- 菜单根据 `permission_codes` 判断是否展示，避免销售员看到无权限页面。
- 风险扫描和经营日报生成按钮调用后端 RQ 触发接口；如果 Redis/RQ 没启动，会显示后端错误提示。
- 审批台支持批准和驳回，批准后后端会创建正式销售任务。
- Agent Trace V1 当前展示 Agent Run 列表，节点级 Step 详情下一版补接口。

## 结论

前端真实 API 工作台已通过生产构建测试，可以进入浏览器联调阶段。下一步建议启动 FastAPI 与 Next.js 开发服务，逐页点击验证登录、菜单权限、审批操作和任务刷新。
