# FastAPI 使用总结（面试问答）

---

## 一、项目中 FastAPI 扮演什么角色？

FastAPI 是本项目的 **Web 服务框架**，负责：
- 接收用户的 HTTP 请求（REST API）
- 将请求路由到 Agent 处理链路
- 返回 AI 生成的回复给前端
- 同时支持 WebSocket 实时通信和静态页面托管

一句话：**前端 ↔ FastAPI ↔ Agent 引擎**，FastAPI 是中间桥梁。

---

## 二、项目里具体写了哪些接口？

### REST 接口（`app/api/routes.py`）

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/api/v1/health` | 健康检查，返回服务状态 |
| `POST` | `/api/v1/chat` | **核心接口**——发送消息，触发 Agent 全链路处理，返回 AI 回复 |
| `GET` | `/api/v1/sessions` | 获取历史会话列表 |
| `GET` | `/api/v1/sessions/{id}` | 获取某个会话的完整消息记录 |
| `DELETE` | `/api/v1/sessions/{id}` | 删除指定会话 |

### WebSocket 接口（`app/api/websocket.py`）

| 路径 | 功能 |
|------|------|
| `WS /api/v1/chat/stream` | 持续连接，支持多轮对话，每次发送"处理中"状态后再返回结果 |

### 页面托管

在 `main.py` 中挂载了 `app/static/` 目录为静态文件，访问 `/` 自动跳转到聊天界面 `chat.html`。

```python
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/chat.html")
```

---

## 三、`POST /api/v1/chat` 接口的处理流程是怎样的？

1. 接收 `ChatRequest`（包含 `session_id`、`message`、`context`）
2. 使用 **Pydantic 自动校验**请求体格式，不合法直接返回 422
3. 生成 `trace_id` 用于全链路追踪
4. 从数据库获取或创建会话
5. 组装 `AgentState`（LangGraph 状态机的输入）
6. 调用 `agent_graph.ainvoke()` 执行 Agent 全链路
7. 拿到 `final_response` 后封装为 `ChatResponse` 返回

关键代码：
```python
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = await agent_graph.ainvoke(initial_state)  # 异步执行 Agent
    return ChatResponse(response=AgentResponse(**final_response))
```

---

## 四、Pydantic 在项目中是怎么用的？

用于 **请求/响应数据校验**和**配置管理**。

### 请求校验
```python
class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: dict = {}
```
FastAPI 收到请求后自动按这个模型校验，`session_id` 和 `message` 缺一不可，类型不对也会报错。

### 响应校验
```python
@router.post("/chat", response_model=ChatResponse)
```
`response_model` 参数让 FastAPI 自动将返回结果按 `ChatResponse` 结构序列化，多余的字段会被过滤掉。

### 配置管理
`configs/` 目录下的 YAML 文件被加载为 Pydantic 对象：
```python
class ModelConfig(BaseModel):
    default_provider: str
    providers: dict[str, ProviderConfig]
    routing: RoutingConfig
```
这样配置有类型提示，拼写错误会立即暴露。

---

## 五、中间件做了什么？

项目写了一个 `TraceMiddleware`（`app/api/middleware.py`），继承 `BaseHTTPMiddleware`：

1. 每个请求进来时生成/提取 `trace_id`
2. 记录请求方法、路径、状态码、耗时
3. 异常时统一返回 500 + 中文错误信息
4. 响应头中注入 `X-Trace-Id`，方便前端排查问题

```python
class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("X-Trace-Id", generate_trace_id())
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
```

---

## 六、启动时做了什么？（lifespan）

FastAPI 的 `lifespan` 是一个异步上下文管理器，在服务启动时自动执行：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：
    import app.tools          # 注册所有工具到 ToolRegistry
    get_llm_provider("router")  # 预热 LLM Provider
    knowledge_base_manager.load_all_domains()  # 加载知识库

    yield  # 服务运行中...

    # 关闭时：
    logger.info("app.shutting_down")
```

面试时可以说："用 lifespan 做启动预热，把 LLM Provider 和知识库提前加载好，避免第一个用户请求时等待过久。"

---

## 七、WebSocket 和普通 HTTP 的区别？为什么项目里两种都有？

| | HTTP（`POST /chat`） | WebSocket（`WS /chat/stream`） |
|---|---|---|
| 连接方式 | 一次请求一次响应 | 建立后保持长连接 |
| 适用场景 | 前端目前的实现 | 预留的流式推送能力 |
| 优势 | 简单、无状态 | 可实时推送处理状态、流式输出 |

项目目前主要用 HTTP，WebSocket 是预留接口——如果以后改成逐字流式输出（像 ChatGPT 那样），WebSocket 比 HTTP 轮询更合适。

---

## 八、面试可能会问的延伸问题

**Q：为什么用 FastAPI 而不是 Flask？**
> FastAPI 原生支持 `async/await`，我们这个项目大量调用外部 API（DeepSeek、数据库），用异步可以避免阻塞其他请求。Flask 是同步的，高并发下性能差很多。

**Q：async/await 在这个项目里具体用在哪里？**
> - `agent_graph.ainvoke()` ——异步执行 Agent 链路
> - `provider.chat()` ——异步调用 LLM API
> - `session_store.add_message()` ——同步但轻量的 SQLite 操作，不会成为瓶颈

**Q：Pydantic 的 model_dump() 是什么？**
> 把 Pydantic 对象转成 Python 字典。比如 `ToolResult.model_dump()` 把工具执行结果转为 dict，方便存入 LangGraph 状态中。

**Q：项目怎么处理错误？**
> 路由层 `try/except` 捕获异常返回 500；中间件兜底捕获未预料的异常；节点内部也有 `try/except`，LLM 调用失败时会降级到 fallback 回复。
