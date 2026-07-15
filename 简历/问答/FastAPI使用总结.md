# FastAPI 使用总结（面试问答）

---

## 一、基础概念解释

### 1. 什么是路由？

路由就是 **"根据 URL 地址，把请求分发给对应的处理函数"**。

比如你打开 `http://xxx.com/api/v1/chat`，服务器收到后根据 `/api/v1/chat` 这个路径，找到对应的函数来执行。就像一个快递分拣中心：看到地址是北京的 → 走北京线；看到是上海的 → 走上海线。

```python
@router.post("/chat")       # URL 是 /chat → 执行 chat() 函数
async def chat(request):
    ...

@router.get("/sessions")    # URL 是 /sessions → 执行 list_sessions() 函数
async def list_sessions():
    ...
```

### 2. 什么是同步和异步？

用现实中的例子理解：

- **同步**：你去奶茶店点一杯奶茶，站在柜台前一直等到做好才走。期间什么也干不了。
- **异步**：你点完奶茶拿个号，然后去旁边便利店买东西，号响了再回来取。等待的时间可以干别的。

程序里的"奶茶"就是**调用外部 API**（比如调 DeepSeek），这个过程可能要 2~30 秒。如果是同步，服务器这期间只能干等着，一个用户就占住了。异步的话，服务器可以在等待期间处理其他用户的请求。

### 3. 什么是 async / await？

`async` 和 `await` 是 Python 写异步代码的语法：

- `async def`：定义一个"可以暂停"的函数
- `await`：在这里暂停，去干别的事，等结果回来了再继续

```python
async def chat(request):
    result = await agent_graph.ainvoke(state)  # 暂停，先去处理别的请求
    return result                               # agent 跑完了，回来继续
```

### 4. 什么是 Pydantic？

Pydantic 是一个**数据校验库**。你定义一个"数据模板"（继承 `BaseModel`），它自动帮你检查数据格式对不对。

比如你规定 `session_id` 必须是字符串，如果前端发了个数字过来，Pydantic 会直接拒绝并返回错误，你不需要手写一堆 `if` 判断。

```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    session_id: str      # 必须是字符串
    message: str         # 必须是字符串
    context: dict = {}   # 可选，默认空字典
```

### 5. 什么是高并发？

高并发就是**同时有很多用户访问，服务器依然能正常响应**。

FastAPI 天生适合高并发，因为它用异步（`async/await`）处理请求。比如 100 个人同时发消息问客服，服务器不是排队一个个处理，而是同时接收、各自等待 AI 返回、谁先返回就先回复谁。

---

## 二、此项目的路由是怎么设计实现的？

项目有两层路由：

### 第一层：HTTP 路由（FastAPI 层）

在 `app/api/routes.py` 中用 `APIRouter` 定义：

```python
router = APIRouter(prefix="/api/v1")  # 所有接口都加上 /api/v1 前缀

@router.get("/health")                # → GET /api/v1/health
@router.post("/chat")                 # → POST /api/v1/chat
@router.get("/sessions")              # → GET /api/v1/sessions
@router.get("/sessions/{id}")         # → GET /api/v1/sessions/xxx  ({id}是动态参数)
@router.delete("/sessions/{id}")      # → DELETE /api/v1/sessions/xxx
```

然后在 `app/main.py` 中注册：
```python
app.include_router(api_router)   # 注册 REST 接口
app.include_router(ws_router)    # 注册 WebSocket 接口
app.mount("/static", ...)        # 托管前端页面
```

### 第二层：Agent 业务路由（LangGraph 层）

代码在 `app/agent/nodes/router.py`，负责判断用户问题属于哪个业务域。

**三层级联**，从快到慢：

| 层 | 方式 | 速度 | 费用 |
|----|------|------|------|
| Layer 1 | 关键词匹配（4个域各有一组关键词，统计命中多少） | 毫秒级 | 免费 |
| Layer 2 | RAG 读取各业务域的说明文档进行匹配 | 秒级 | 免费 |
| Layer 3 | 调大模型（DeepSeek）做最终判断 | 2~30秒 | 花钱 |

另外做了特殊识别：如果用户输入里有订单号（`ORD` + 数字），直接打高分给订单域，跳过 LLM 调用；有手机号同理。

路由出结果后，根据业务域自动选择调用哪些工具：
```python
"account":    → FAQ检索 + 账户查询
"order":      → FAQ检索 + 订单查询（物流信息）
"after_sale": → FAQ检索 + 创建工单
```

---

## 三、我在此项目用 FastAPI 实现了什么？

### 1. 核心对话接口 `POST /api/v1/chat`

整个项目最关键的接口。流程：
1. 前端发来 `{session_id, message}`
2. Pydantic 自动校验格式
3. 生成 `trace_id` 全程追踪
4. 从 SQLite 加载历史会话（实现上下文记忆）
5. 组装 Agent 状态 → 执行 LangGraph 全链路（澄清→路由→检索→回复）
6. 返回 AI 回复和快捷回复按钮

```python
@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = await agent_graph.ainvoke(initial_state)  # 异步执行
    return ChatResponse(response=AgentResponse(**final_response))
```

### 2. 历史会话管理（3 个接口）

`GET /sessions` — 列出所有历史会话；`GET /sessions/{id}` — 查看某次对话的完整记录；`DELETE /sessions/{id}` — 删除会话。数据存在 SQLite 中。

### 3. 健康检查 `GET /api/v1/health`

返回服务状态、版本号、当前可用的 LLM Provider。K8s/Docker 用来判断服务是否还活着。

### 4. WebSocket 实时通信（预留）

`WS /api/v1/chat/stream` — 长连接模式，先在聊天中发送"处理中"状态，再把 AI 回复推回去，为以后做逐字流式输出（像 ChatGPT 那样）做准备。

### 5. 托管前端页面

把 `chat.html` 挂载到 `/static/` 目录下，访问 `/` 自动跳转。用户打开网址就能直接用。

### 6. 中间件：请求追踪 + 异常兜底

每个请求自动分配 `trace_id`，记录到日志中；出了异常统一返回中文错误信息，不给用户看报错堆栈。

### 7. 启动预热

服务启动时自动加载所有工具、预热 LLM Provider、加载知识库——让第一个用户不用等。

---

## 四、面试可能追问

**Q：为什么用 FastAPI 而不用 Flask？**
> FastAPI 原生支持 `async/await`（异步），本项目大量调用外部 API（DeepSeek），用异步等待时可以去处理别的请求，高并发下性能更好。Flask 默认是同步的。

**Q：项目里哪里用了 async/await？**
> `POST /chat` 接口用 `async def`；调用 `agent_graph.ainvoke()` 时用 `await` 挂起等待；调用 LLM API 也是异步的。

**Q：Pydantic 的好处？**
> 不用手写校验。定义好 `ChatRequest`，字段类型、是否必填 Pydantic 全自动检查，不合法直接返回 422，既省代码又安全。

**Q：项目怎么处理错误？**
> 三层兜底：路由层 `try/except` → 中间件统一捕获 → Agent 节点内部 LLM 失败时走降级回复。
