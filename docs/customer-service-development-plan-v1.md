# 客服服务平台开发计划 V1.0

| 任务编号 | 任务名称 | 对应需求 | 涉及文件或模块 | 前置依赖 | 交付结果 | 验证方式 | 优先级 |
|---|---|---|---|---|---|---|---|
| DEV-01 | 领域类型与状态机 | CS-FN-002/005/007/009/011 | `app/support/models.py`,`state_machine.py` | 无 | 类型与合法转换 | 单元测试 | P0 |
| DEV-02 | SQLite 支持存储 | CS-FN-005/007/009/010/011/012 | `app/support/store.py` | DEV-01 | 增量表、事务、所有权 | 单元/API | P0 |
| DEV-03 | Mock 业务适配器 | CS-FN-002/005/010 | `app/support/adapters.py` | DEV-01 | 集中 Mock、边界标记、失败模式 | 单元测试 | P0 |
| DEV-04 | 统一 SupportService | CS-FN-001～012 | `app/support/service.py`,`policy.py` | DEV-01～03 | 编排、幂等、审计、降级 | 集成测试 | P0 |
| DEV-05 | 身份角色与 API | CS-FN-001～005/007～012 | `app/core/auth.py`,`app/api/support.py` | DEV-04 | REST 契约与 RBAC | API 测试 | P0 |
| DEV-06 | 智能客服策略接入 | CS-FN-006/007 | `app/agent/service.py`,`support/policy.py` | DEV-04 | 人工直达、两次未解、摘要 | Agent 测试 | P0 |
| DEV-07 | 用户服务台结构 | CS-FN-001～007/009～011 | `app/static/chat.html`,`css`,`js` | DEV-05 | 首页、会话、进度、状态 | UI smoke | P0 |
| DEV-08 | FAQ 与自助 UI | CS-FN-003～005 | 前端 modules | DEV-07 | 搜索、详情、反馈、自助任务 | UI/API | P0/P1 |
| DEV-09 | 人工/工单/评价 UI | CS-FN-007/009～011 | 前端 modules | DEV-07 | 排队、工单时间线、评价 | UI/API | P0 |
| DEV-10 | 演示坐席工作台 | CS-FN-008/012 | `agent.html`,`agent.js` | DEV-05 | 授权任务、状态处理、审计摘要 | 权限/UI | P0/P1 |
| DEV-11 | 安全与异常完善 | 全部 | middleware/service/UI | DEV-01～10 | 脱敏、错误、重试、Mock 标记 | 专项测试 | P0 |
| DEV-12 | 全量验证与文档 | 全部 | tests/scripts/README/docs | 全部 | 验收报告与运行说明 | 全命令 | P0 |

## 批次

1. 基础骨架：DEV-01～04。
2. 入口与上下文：DEV-05 + 用户首页骨架。
3. FAQ 与自助：DEV-08。
4. 智能客服：DEV-06。
5. 人工与工单：DEV-09～10。
6. 评价、权限、埋点与完善：DEV-11～12。

每批完成后执行 compileall、相关 pytest、全量 pytest、启动/OpenAPI smoke；涉及 UI 的批次增加桌面/移动浏览器验证并更新追踪矩阵。

## 完成状态（2026-07-22）

- DEV-01～DEV-11：已实现并完成对应单元、API 或浏览器验证。
- DEV-12：已完成 README、技术设计、追踪矩阵、测试计划和阶段三验收报告。
- 未纳入本期完成声明：真实订单/课程/支付/认证/通知/坐席适配器、生产运营后台和多实例存储迁移。
