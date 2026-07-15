# 智能客服 Agent 系统 (SCS-Agent)

🚀 **在线体验**：https://smart-customer-service-8djy.onrender.com/static/chat.html

基于 LangGraph + DeepSeek 的生产级智能客服系统，支持多轮对话、工具调用、RAG 知识库、历史会话管理。

## 功能特性

- **多轮对话** — LangGraph 状态机驱动，自动反问澄清模糊问题
- **智能路由** — 关键词 + RAG + LLM 三层路由，精准匹配业务域
- **工具调用** — FAQ 检索 / 订单查询 / 账户查询 / 工单 / 转人工
- **物流查询** — 内置 12 条真实物流数据，支持按订单号/手机号/关键词查询
- **RAG 知识库** — 4 个业务域 × 40 条 FAQ，混合检索（向量 + BM25）+ 重排
- **多模型** — DeepSeek / OpenAI / Claude / Qwen 可切换
- **历史会话** — SQLite 持久化，支持恢复对话、AI 记住上下文
- **弹性机制** — 熔断 / 指数退避重试 / 限流
- **美观界面** — 淘宝/天猫/京东风格电商客服 UI

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入 DeepSeek API Key：

```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
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
│   │   ├── state.py             # AgentState 定义
│   │   └── nodes/               # 5 个节点 (clarify/router/executor/respond/fallback)
│   ├── llm/                     # LLM Provider 抽象层
│   │   └── {openai,claude,qwen,mock}_provider.py
│   ├── rag/                     # RAG 知识库 (ChromaDB + BM25 + Rerank)
│   ├── tools/                   # 工具注册 + 6 个内置工具
│   ├── resilience/              # 熔断/重试/限流
│   ├── prompts/templates/       # YAML 模板化 Prompt
│   ├── core/                    # 配置/会话/日志/DI
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
| POST | `/api/v1/chat` | 发送消息 |
| GET | `/api/v1/sessions` | 历史会话列表 |
| GET | `/api/v1/sessions/{id}` | 会话详情 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| GET | `/api/v1/health` | 健康检查 |

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
