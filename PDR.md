# 智能客服 Agent 项目需求文档（PRD）

---

## 一、项目概述

### 1.1 项目名称
Smart Customer Service Agent（简称 SCS-Agent）

### 1.2 项目目标
构建一个面向真实业务场景的智能客服 Agent 系统，能够：
- 处理多轮、模糊、复杂的用户咨询
- 通过 RAG + Function Calling 路由到正确的业务知识与系统能力
- 支持高并发、异步、可观测、可降级的生产级运行
- 支持多模型切换、提示词版本管理、知识库热更新

### 1.3 技术栈
| 层级 | 技术选型 |
|---|---|
| Agent 框架 | LangChain + LangGraph（多轮状态机） |
| 大模型 | OpenAI GPT-4o / Claude / Qwen（可切换） |
| 向量库 | Milvus / Qdrant（可切换） |
| 关系型存储 | PostgreSQL（会话、日志、配置） |
| 缓存 | Redis（会话上下文、限流、熔断状态） |
| 消息队列 | RabbitMQ / Kafka（异步任务、人工转接） |
| 后端框架 | FastAPI（异步 IO） |
| 部署 | Docker + Kubernetes（集群） |
| 监控 | Prometheus + Grafana + LangSmith |

---

## 二、核心业务需求

### 2.1 多轮对话与反问机制（NLU 澄清层）

#### 2.1.1 场景描述
用户首次提问往往是模糊的，例如：
- "你们那个功能不好用了"
- "我想办那个业务，怎么弄"

直接 FAQ 向量匹配无法命中，需要 Agent 主动反问澄清。

#### 2.1.2 功能要求
1. **意图模糊度评估**：对用户输入进行模糊度打分（0-1），低于阈值时触发反问
2. **反问策略生成**：
   - 划定范围式反问："您说的是 A 业务还是 B 业务？"
   - 预选项反问：给出 2-4 个候选问题供用户选择
   - 补充信息式反问：明确告知缺失的关键信息字段
3. **多模态回复支持**：反问及回复需支持文本 + 图片 + 视频卡片混合输出
4. **澄清轮次限制**：最多反问 2 轮，仍无法明确则进入兜底流程（见 2.5）
5. **上下文继承**：反问过程中保留已获取的信息，避免重复询问

#### 2.1.3 接口约定
```python
class ClarifyResult(BaseModel):
    need_clarify: bool
    clarify_type: Literal["scope", "options", "supplement"]
    clarify_message: str
    options: list[str] | None  # 预选项
    missing_fields: list[str] | None  # 缺失关键字段
    confidence: float
```

---

### 2.2 智能路由设计（Router Layer）

#### 2.2.1 设计原则
> 不依赖大模型基座知识做分类，而是通过 **RAG + 人工细分知识库 + Function Calling** 实现有依据的路由。

#### 2.2.2 路由架构
```
用户输入
   │
   ▼
┌─────────────────────────┐
│  Layer 1: 意图粗分类     │  ← 基于规则 + 关键词 + 小模型快速分类
│  (intent coarse router)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Layer 2: 知识库路由     │  ← RAG 检索各业务域知识库摘要
│  (kb route via RAG)      │     返回 top-K 候选业务域
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Layer 3: LLM 精细路由   │  ← LLM 基于 RAG 结果 + 用户上下文
│  (llm fine router)       │     + 可用 tools 做有依据的 function call
└──────────┬──────────────┘
           │
     ┌─────┴──────┬──────────┐
     ▼            ▼          ▼
  FAQ检索     工单系统     业务API调用
```

#### 2.2.3 知识库细分策略
- 按业务线（如：账户、支付、订单、售后）划分独立知识库
- 每个知识库维护一份 **业务域摘要文件（domain_summary.md）**，包含：
  - 业务域名称、边界描述
  - 常见意图列表
  - 关联的 tools / API
  - 关联的 FAQ 列表 ID
- 路由时先检索摘要，再决定进入哪个知识库做精细 RAG

#### 2.2.4 路由可观测性
- 每次路由决策记录：粗分类结果、RAG 候选、LLM 决策、决策依据
- 路由准确率埋点：用户后续是否转人工 / 是否重新提问

---

### 2.3 知识库与 FAQ 系统（RAG Layer）

#### 2.3.1 FAQ 结构化设计
```python
class FAQItem(BaseModel):
    id: str
    domain: str  # 业务域
    question: str
    answer: str
    answer_multimedia: list[MultimediaItem]  # 图片/视频/卡片
    keywords: list[str]
    related_faqs: list[str]
    version: int
    status: Literal["active", "draft", "archived"]
```

#### 2.3.2 检索策略
- **混合检索**：向量检索（语义） + BM25（关键词） + 业务域过滤
- **Rerank**：使用 Cross-Encoder 对 top-20 重排，取 top-5
- **多模态索引**：图片通过 vision model 生成描述后入向量库

#### 2.3.3 知识库热更新
- 知识库新增/修改时，通过消息队列异步触发重新 embedding
- 支持灰度发布：新知识先进入 draft 状态，A/B 测试后激活
- 版本管理：每次更新保留历史版本，可回滚

---

### 2.4 工具与外部系统集成（Tool Layer）

#### 2.4.1 内置工具集
| 工具名 | 功能 | 调用方式 |
|---|---|---|
| `faq_search` | FAQ 知识库检索 | 向量+关键词 |
| `query_order` | 订单系统查询 | REST API |
| `query_account` | 账户系统查询 | REST API |
| `create_ticket` | 创建工单 | REST API |
| `transfer_human` | 转人工 | 消息队列 |
| `policy_search` | 政策/规则检索 | RAG |

#### 2.4.2 工具注册机制
```python
# 工具通过装饰器注册，支持动态加载
@tool_registry.register(
    name="query_order",
    domain="order",
    description="查询用户订单状态",
    params_schema=QueryOrderParams,
    fallback=static_fallback  # 降级回调
)
async def query_order(params: QueryOrderParams) -> ToolResult:
    ...
```

---

### 2.5 兜底与降级机制（Fallback Layer）

#### 2.5.1 降级链路
```
正常 LLM Agent 响应
   │ 失败/超时
   ▼
LLM 熔断降级 → 纯规则 + RAG 检索回复（无 LLM 生成）
   │ 仍无法解决
   ▼
排队提示 → 异步生成回复，稍后推送
   │ 排队超时
   ▼
转人工客服
```

#### 2.5.2 兜底触发条件
| 条件 | 动作 |
|---|---|
| LLM 调用连续失败 3 次 | 熔断，降级到纯 RAG |
| LLM 响应超时 > 15s | 触发排队提示 |
| 澄清轮次 > 2 仍不明确 | 转人工 |
| 用户主动要求人工 | 立即转人工 |
| 业务系统 API 不可用 | 返回已知静态信息 + 工单兜底 |

---

### 2.6 多模态回复

#### 2.6.1 回复类型
- 纯文本
- 文本 + 图片（操作截图）
- 文本 + 视频卡片（教学视频）
- 文本 + 交互卡片（按钮、表单）
- 富文本（Markdown 渲染）

#### 2.6.2 回复结构
```python
class AgentResponse(BaseModel):
    text: str
    multimedia: list[MultimediaItem]
    quick_replies: list[QuickReply]  # 快捷回复按钮
    action: Literal["reply", "clarify", "transfer_human", "create_ticket"] | None
    metadata: dict  # 路由信息、检索来源等
```

---

## 三、非功能性需求

### 3.1 高并发与异步

#### 3.1.1 架构要求
- 全链路异步：FastAPI + async/await，IO 密集型操作不阻塞
- 会话级并发：每个用户会话独立协程，互不阻塞
- LLM 调用并发控制：
  - 信号量限制单实例最大并发 LLM 调用数（可配置）
  - 多实例部署时通过 Redis 做全局并发计数
- 请求队列：超过并发上限的请求进入 Redis 队列，前端轮询/WebSocket 推送结果

#### 3.1.2 性能指标
| 指标 | 目标 |
|---|---|
| 单实例并发会话 | ≥ 100 |
| P95 响应延迟 | ≤ 5s（含 LLM） |
| 降级模式响应 | ≤ 1s |
| 集群横向扩容 | 支持 K8s HPA 自动扩缩 |

---

### 3.2 健壮性与治理

#### 3.2.1 错误处理
- 全局异常捕获中间件
- 每一层（路由、RAG、Tool、LLM）独立 try-catch + 结构化日志
- 错误分类：可重试 / 不可重试 / 需降级 / 需转人工

#### 3.2.2 熔断机制
```python
# 基于 Redis 的分布式熔断器
class CircuitBreaker:
    """
    状态机：closed → open → half_open → closed
    - 连续失败 N 次 → open（拒绝调用，走降级）
    - 等待 cooldown 秒后 → half_open（放行 1 个探测请求）
    - 探测成功 → closed；失败 → open
    """
    failure_threshold: int = 5
    cooldown_seconds: int = 60
    half_open_max_calls: int = 1
```

#### 3.2.3 重试机制
- LLM 调用：指数退避重试，最多 3 次，初始 1s
- Tool API 调用：固定间隔重试，最多 3 次
- RAG 检索：无重试（直接降级到关键词匹配）
- 重试幂等性：所有 Tool 调用需支持幂等 key

#### 3.2.4 Agent 治理
- 每次会话生成唯一 trace_id，全链路传递
- LangSmith 集成，记录每步 LLM 调用的 prompt、output、token、latency
- 关键指标埋点：路由准确率、FAQ 命中率、转人工率、用户满意度

---

### 3.3 提示词管理

#### 3.3.1 版本管理
```
prompts/
├── system/
│   ├── router_prompt.yaml
│   ├── clarify_prompt.yaml
│   ├── answer_prompt.yaml
│   └── fallback_prompt.yaml
├── v1.0/
│   └── ...  # 历史版本快照
└── prompt_config.yaml  # 当前生效版本配置
```

#### 3.3.2 模板化设计
```yaml
# router_prompt.yaml
name: router_prompt
version: "1.2"
variables:
  - user_input
  - chat_history
  - domain_summaries  # RAG 检索的业务域摘要
  - available_tools
template: |
  你是一个智能客服路由助手。
  
  可用业务域：
  {domain_summaries}
  
  可用工具：
  {available_tools}
  
  用户问题：{user_input}
  历史对话：{chat_history}
  
  请判断应该路由到哪个业务域，或调用哪个工具。
  必须给出判断依据。
```

#### 3.3.3 提示词自动生成辅助
- 提供 prompt 生成工具，输入业务域描述自动生成初版 prompt
- 支持 A/B 测试：同时运行两个版本 prompt，对比效果

---

### 3.4 模型层可替换性

#### 3.4.1 模型抽象层
```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[Message], **kwargs) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_with_tools(
        self, messages: list[Message], tools: list[Tool], **kwargs
    ) -> LLMResponse:
        ...

# 具体实现
class OpenAIProvider(LLMProvider): ...
class ClaudeProvider(LLMProvider): ...
class QwenProvider(LLMProvider): ...
```

#### 3.4.2 配置驱动切换
```yaml
# model_config.yaml
default_provider: openai
providers:
  openai:
    model: gpt-4o
    api_key: ${OPENAI_API_KEY}
    timeout: 15
    max_retries: 3
  claude:
    model: claude-sonnet-4-20250514
    api_key: ${ANTHROPIC_API_KEY}
  qwen:
    model: qwen-max
    api_key: ${DASHSCOPE_API_KEY}

# 按场景分配
routing:
  router: openai       # 路由用便宜快模型
  clarify: openai
  answer: claude       # 生成回复用强模型
  fallback: qwen       # 降级用国产模型
```

---

### 3.5 知识库与路由可扩展性

#### 3.5.1 新增业务域流程
1. 在 `domains/` 下新建业务域目录
2. 编写 `domain_summary.md`（自动被索引）
3. 导入该业务域的 FAQ / 文档
4. 系统自动触发 embedding，无需重启
5. 路由层自动纳入新业务域候选

#### 3.5.2 目录结构
```
knowledge_base/
├── domains/
│   ├── account/
│   │   ├── domain_summary.md
│   │   ├── faqs/
│   │   ├── docs/
│   │   └── multimedia/
│   ├── payment/
│   ├── order/
│   └── after_sale/
├── global/              # 全局通用知识
└── index_config.yaml    # 索引配置
```

---

## 四、系统架构总览

```
                         ┌─────────────┐
                         │   用户端     │
                         │ (Web/小程序) │
                         └──────┬──────┘
                                │ WebSocket / HTTP
                                ▼
                    ┌───────────────────────┐
                    │   API Gateway (FastAPI)│
                    │   限流 / 鉴权 / 路由    │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Session Manager       │
                    │  会话状态管理          │
                    └───────────┬───────────┘
                                │
              ┌─────────────────▼─────────────────┐
              │         Agent Orchestrator          │
              │         (LangGraph State Machine)   │
              │                                     │
              │  ┌─────────┐  ┌──────────┐         │
              │  │ Clarify │  │  Router  │         │
              │  │  Node   │  │  Node    │         │
              │  └────┬────┘  └────┬─────┘         │
              │       │            │                │
              │  ┌────▼────────────▼─────┐         │
              │  │   Executor Node        │         │
              │  │ (RAG + Tool Calling)   │         │
              │  └────────────┬───────────┘         │
              │               │                     │
              │  ┌────────────▼───────────┐         │
              │  │  Response Generator     │         │
              │  └────────────┬───────────┘         │
              │               │                     │
              │  ┌────────────▼───────────┐         │
              │  │  Fallback / Transfer    │         │
              │  └────────────────────────┘         │
              └─────────────────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                    ▼
    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
    │ LLM Provider│    │ Vector Store │    │  Tool Layer  │
    │ (可切换)     │    │ (Milvus)     │    │ (业务API)     │
    └─────────────┘    └──────────────┘    └──────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌──────────────────────────────────────────────────────┐
    │           Observability (LangSmith / Prometheus)      │
    └──────────────────────────────────────────────────────┘
```

---

## 五、LangGraph 状态机设计

```python
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    messages: list[BaseMessage]
    session_id: str
    user_input: str
    clarify_count: int
    router_result: dict | None
    rag_context: list[dict]
    tool_calls: list[dict]
    final_response: AgentResponse | None
    should_transfer_human: bool
    trace_id: str

graph = StateGraph(AgentState)

graph.add_node("clarify", clarify_node)
graph.add_node("router", router_node)
graph.add_node("executor", executor_node)       # RAG + Tool Call
graph.add_node("respond", respond_node)
graph.add_node("fallback", fallback_node)

graph.set_entry_point("clarify")

graph.add_conditional_edges("clarify", route_after_clarify, {
    "need_clarify": "respond",      # 反问
    "ready": "router",
    "give_up": "fallback",
})

graph.add_edge("router", "executor")
graph.add_conditional_edges("executor", route_after_execute, {
    "need_more_tools": "executor",  # 循环调用工具
    "ready": "respond",
    "error": "fallback",
})
graph.add_edge("respond", END)
graph.add_edge("fallback", END)
```

---

## 六、项目目录结构

```
smart-customer-service/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── api/
│   │   ├── routes.py              # API 路由
│   │   └── websocket.py           # WebSocket 处理
│   ├── agent/
│   │   ├── graph.py               # LangGraph 状态机定义
│   │   ├── nodes/
│   │   │   ├── clarify.py
│   │   │   ├── router.py
│   │   │   ├── executor.py
│   │   │   ├── respond.py
│   │   │   └── fallback.py
│   │   └── state.py               # AgentState 定义
│   ├── core/
│   │   ├── config.py              # 配置管理
│   │   ├── session.py             # 会话管理
│   │   └── observability.py       # 链路追踪
│   ├── llm/
│   │   ├── provider.py            # LLM 抽象层
│   │   ├── openai_provider.py
│   │   ├── claude_provider.py
│   │   └── factory.py             # 工厂模式
│   ├── rag/
│   │   ├── indexer.py             # 索引构建
│   │   ├── retriever.py           # 检索器
│   │   ├── reranker.py            # 重排器
│   │   └── knowledge_base.py      # 知识库管理
│   ├── tools/
│   │   ├── registry.py            # 工具注册中心
│   │   ├── faq_search.py
│   │   ├── query_order.py
│   │   ├── create_ticket.py
│   │   └── transfer_human.py
│   ├── resilience/
│   │   ├── circuit_breaker.py     # 熔断器
│   │   ├── retry.py               # 重试
│   │   └── rate_limiter.py        # 限流
│   └── prompts/
│       ├── manager.py             # Prompt 版本管理
│       └── templates/             # YAML 模板
├── knowledge_base/
│   ├── domains/
│   │   ├── account/
│   │   ├── payment/
│   │   ├── order/
│   │   └── after_sale/
│   └── global/
├── configs/
│   ├── model_config.yaml
│   ├── prompt_config.yaml
│   └── index_config.yaml
├── tests/
├── docker/
├── pyproject.toml
└── README.md
```

---

## 七、开发阶段划分

### Phase 1：核心链路 MVP（2 周）
- [ ] LangGraph 状态机搭建（clarify → router → executor → respond）
- [ ] 单一 LLM Provider（OpenAI）接入
- [ ] 基础 RAG 检索（单业务域 FAQ）
- [ ] FastAPI 接口 + 会话管理
- [ ] 基础反问机制

### Phase 2：路由与多业务域（2 周）
- [ ] 三层路由架构实现
- [ ] 多业务域知识库划分 + domain_summary
- [ ] 混合检索（向量 + BM25）+ Rerank
- [ ] 工具注册机制 + 3 个核心工具

### Phase 3：工程化与健壮性（2 周）
- [ ] 熔断 / 重试 / 降级机制
- [ ] 多模型 Provider 抽象 + 配置切换
- [ ] Prompt 版本管理 + YAML 模板化
- [ ] 全链路 trace + LangSmith 集成
- [ ] 知识库热更新

### Phase 4：高并发与部署（1 周）
- [ ] 异步并发优化 + 信号量控制
- [ ] Redis 会话存储 + 分布式限流
- [ ] Docker 镜像 + K8s 部署配置
- [ ] Prometheus + Grafana 监控面板

### Phase 5：多模态与体验优化（1 周）
- [ ] 多模态回复支持
- [ ] A/B 测试框架
- [ ] 用户满意度反馈闭环
- [ ] 人工转接流程打通

---

## 八、关键接口约定

### 8.1 对话接口
```http
POST /api/v1/chat
Content-Type: application/json

{
  "session_id": "sess_xxx",
  "message": "我的订单怎么还没发货",
  "context": {
    "user_id": "u_xxx",
    "channel": "web"
  }
}

Response:
{
  "response": {
    "text": "您好，我帮您查询一下订单状态...",
    "multimedia": [],
    "quick_replies": ["查看物流详情", "联系人工"],
    "action": "reply",
    "metadata": {
      "trace_id": "trace_xxx",
      "router_domain": "order",
      "rag_sources": ["faq_123", "faq_456"]
    }
  }
}
```

### 8.2 WebSocket 流式接口
```http
WS /api/v1/chat/stream?session_id=sess_xxx
```
服务端逐步推送 `AgentResponseChunk`，前端流式渲染。

---

## 九、给 Claude Code 的开发指引

1. **先读 `configs/` 下所有 YAML**，理解配置驱动的架构
2. **从 `app/agent/graph.py` 开始**，理解状态机流转
3. **每个 Node 的输入输出严格遵循 `AgentState`**，不要引入隐式状态
4. **所有 LLM 调用必须经过 `llm/provider.py` 抽象层**，禁止直接调用 SDK
5. **所有外部调用必须包裹 `resilience/` 下的熔断 + 重试装饰器**
6. **Prompt 从 `prompts/templates/` 加载**，禁止硬编码在代码中
7. **新增业务域只需在 `knowledge_base/domains/` 下建目录**，无需改代码
8. **每个模块需附带单元测试**，Agent 链路需有集成测试
9. **日志统一使用 structlog**，每条日志带 `trace_id` 和 `session_id`
10. **类型注解全覆盖**，使用 Pydantic 做运行时校验

---
