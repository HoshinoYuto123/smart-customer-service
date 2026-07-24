# 客服服务平台需求追踪矩阵 V1.0

> 状态随开发批次更新。Mock 表示可运行的替换层，不代表真实外部系统已接入。

| PRD需求编号 | 需求名称 | 用户场景 | 优先级 | 前端页面或组件 | 后端模块 | 数据模型 | 接口 | 测试用例 | 当前状态 |
|---|---|---|---|---|---|---|---|---|---|
| CS-FN-001 | 多场景客服入口 | CS-SC-001～020 | P0 | ServiceDesk、主导航、业务入口卡 | Support Catalog | User/Session | API-003 | TC-001/002 | 已实现并验证 |
| CS-FN-002 | 身份与业务上下文 | CS-SC-001～020 | P0 | ContextSelector | Identity/Support Context | User/Session | API-001/004/009 | TC-003/004/018 | 已实现（业务对象为 Mock） |
| CS-FN-003 | 分类、搜索与推荐 | CS-SC-001/002/015/017 | P1 | CategoryRail/FAQSearch | Support Catalog | FAQCategory | API-005/006 | TC-005/006 | 已实现并验证 |
| CS-FN-004 | 上下文 FAQ | CS-SC-001/002/013/015 | P0 | FAQCard/FAQDetail | Catalog/FAQ adapter | FAQArticle/Feedback | API-006～008 | TC-007/008 | 已实现并验证 |
| CS-FN-005 | 高频自助服务 | CS-SC-001～014/016 | P0 | SelfServicePanel | Self Service | SelfServiceTask | API-011/012 | TC-009～011/020 | 已实现（执行为 Mock） |
| CS-FN-006 | 智能客服 | CS-SC-015/017/018 | P0 | Conversation/QuickReply | LangGraph/Policy | Message/Intent | API-009/010 | TC-012～014 | 已实现并验证 |
| CS-FN-007 | 转人工与排队 | CS-SC-007～011/016～019 | P0 | Transfer/QueuePanel | Human Queue | QueueEntry | API-013～015 | TC-015～017 | 已实现异步承接；在线队列待接入 |
| CS-FN-008 | 人工客服工作台 | CS-SC-007～011/016～020 | P0 | AgentWorkspace | Agent Workspace/RBAC | Agent/AgentConversation | API-002/016/020 | TC-018/019 | 已实现演示工作台并验证 |
| CS-FN-009 | 工单与服务进度 | CS-SC-003/006/007/011/014/016/019/020 | P0 | TicketList/Detail/Timeline | Ticket & Progress | Ticket/Comment/History | API-017～022 | TC-020～023 | 已实现并验证 |
| CS-FN-010 | 服务消息通知 | CS-SC-006/007/011/014/019/020 | P1 | ProgressTimeline/Notification | Notification | Notification | API-022 | TC-024 | 已实现站内 Mock；外部通知待接入 |
| CS-FN-011 | 结束与满意度 | CS-SC-001～020 | P0 | RatingPanel | Resolution & Rating | SatisfactionRating | API-023 | TC-025/026 | 已实现并验证 |
| CS-FN-012 | 客服运营后台 | 全部 | P1（最小配置/审计） | Agent/Ops summary | Ops/Analytics/Audit | AuditLog/Event | API-024 | TC-027/028 | 已实现事件/审计；完整运营配置待后续 |

## 冲突与假设

| 冲突编号 | PRD需求编号 | 冲突内容 | 技术影响 | 建议方案 | 当前处理 |
|---|---|---|---|---|---|
| CON-001 | CS-FN-007/009 | 现有 Mock 写死排队人数、等待 30 秒与响应 2 小时，PRD 明确这些参数待确认 | 形成虚假承诺 | 删除数值，返回可配置/待确认状态 | 本期修复 |
| CON-002 | CS-FN-002/005 | 现有演示订单查询不校验资源所有权 | 越权与隐私风险 | 新 API 强制 owner；旧工具仅返回脱敏演示结果 | 本期修复 |
| CON-003 | CS-FN-008/012 | 无真实坐席身份系统 | 无法生产授权 | demo 模式签发演示角色；production 禁止 | Mock 边界 |
| CON-004 | CS-FN-005/010 | 无真实支付、课程、通知系统 | 不能执行真实动作 | 可替换 Mock adapter，所有响应带 `data_mode=mock` | Mock 边界 |
