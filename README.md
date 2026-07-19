# 智能客服 Agent 系统 (SCS-Agent)

🚀 **在线体验**：https://smart-customer-service-8djy.onrender.com/static/chat.html

基于 LangGraph + DeepSeek 的智能客服参考实现，支持多轮对话、工具调用、RAG 知识库、会话隔离与历史管理。项目默认以 `demo` 模式运行；接入真实业务 API 和外部会话存储后再用于生产环境。

## 功能特性

- **多轮对话** — LangGraph 状态机驱动，自动反问澄清模糊问题
- **智能路由** — 关键词 + 业务域摘要 + LLM 路由，保守选择业务工具
- **工具调用** — FAQ 检索 / 订单查询 / 账户查询 / 工单 / 转人工
- **物流查询** — 内置带明确标记的演示物流数据；查不到时不会伪造订单
- **RAG 知识库** — 4 个业务域 × 40 条 FAQ，混合检索（向量 + BM25）+ 重排
- **多模型** — DeepSeek / OpenAI / Claude / Qwen 可切换
- **历史会话** — 签名 HttpOnly 身份 Cookie + SQLite 所有权隔离，持久化对话和澄清状态
- **弹性机制** — LLM/工具统一接入并发上限、队列、超时、熔断和指数退避重试
- **美观界面** — 淘宝/天猫/京东风格电商客服 UI

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

创建 `.env`，至少填入 DeepSeek API Key。生产模式还必须配置共享的高强度 `AUTH_SECRET`：

```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
APP_MODE=demo
AUTH_SECRET=replace-with-a-long-random-secret
```

### 3. 启动服务

```bash
python -m app.main
```

### 4. 打开界面

浏览器访问 **https://smart-customer-service-8djy.onrender.com/static/chat.html**

## 项目结构

```
smart-customer-service/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── agent/
│   │   ├── graph.py             # LangGraph 状态机
│   │   ├── service.py           # 单轮执行与状态持久化
│   │   ├── state.py             # AgentState 定义
│   │   └── nodes/               # 5 个节点 (clarify/router/executor/respond/fallback)
│   ├── llm/                     # LLM Provider 抽象层
│   │   └── {openai,claude,qwen,mock}_provider.py
│   ├── rag/                     # RAG 知识库 (ChromaDB + BM25 + Rerank)
│   ├── tools/                   # 工具注册 + 6 个内置工具
│   ├── resilience/              # 熔断/重试/限流
│   ├── prompts/templates/       # YAML 模板化 Prompt
│   ├── core/                    # 配置/身份/会话/日志/DI
│   ├── api/                     # REST + WebSocket 接口
│   └── static/                  # 聊天前端页面
├── knowledge_base/
│   ├── domains/                 # 4 个业务域 FAQ + 摘要
│   └── logistics_db.json       # 物流信息数据库
├── configs/                     # YAML 配置文件
├── tests/                       # 单元测试 + 集成测试
├── docker/                      # Docker 部署
└── k8s/                         # K8s 部署
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 聊天界面 |
| POST | `/api/v1/auth/anonymous` | 签发匿名身份 Cookie |
| POST | `/api/v1/chat` | 发送消息 |
| GET | `/api/v1/sessions` | 历史会话列表 |
| GET | `/api/v1/sessions/{id}` | 会话详情 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/health/live` | K8s 存活检查 |
| GET | `/api/v1/health/ready` | 依赖就绪检查 |

除健康检查和身份签发外，API 需要 `scs_auth` Cookie（或 Bearer Token）。会话始终按身份所有者过滤。

## 运行模式与部署限制

- `APP_MODE=demo`：允许使用内置订单、账户、工单和人工队列演示适配器，响应中包含 `is_demo_data=true`。
- `APP_MODE=production`：未配置真实业务适配器时失败关闭，不返回模拟数据。
- `SKIP_EMBEDDING_MODEL=1`：关闭向量检索并安全降级为中文 BM25；适合没有预装模型的轻量部署。
- 当前会话存储仍为 SQLite，因此 K8s 配置固定为单副本并挂载 PVC。迁移到 PostgreSQL/Redis 后才能重新开启 HPA。

## 技术栈

| 层级 | 选型 |
|------|------|
| Agent 框架 | LangGraph |
| LLM | DeepSeek / OpenAI / Claude / Qwen |
| 向量库 | ChromaDB |
| 后端 | FastAPI |
| 存储 | SQLite |
| 前端 | 原生 HTML/CSS/JS |
| 部署 | Docker + K8s |

## License

MIT
