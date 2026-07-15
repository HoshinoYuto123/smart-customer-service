from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agent.types import ChatRequest, ChatResponse, HealthResponse, AgentResponse
from app.agent.state import AgentState
from app.agent.graph import agent_graph
from app.core import session_store
from app.core.di import get_session_manager
from app.core.observability import get_trace_id, set_trace_id, set_session_id, generate_trace_id, get_logger
from app.core.config import get_model_config, get_app_config

router = APIRouter(prefix="/api/v1")
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    config = get_model_config()
    app_config = get_app_config()
    return HealthResponse(
        status="ok",
        version=app_config.app.version,
        providers=list(config.providers.keys()),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id
    message = request.message.strip()
    user_id = request.context.get("user_id", "")
    channel = request.context.get("channel", "web")
    trace_id = generate_trace_id()

    set_trace_id(trace_id)
    set_session_id(session_id)

    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    logger.info("chat.request", session_id=session_id, message=message[:200], trace_id=trace_id)

    session_mgr = get_session_manager()
    session = await session_mgr.get_or_create(session_id, user_id=user_id, channel=channel)

    # Build initial state
    initial_state: AgentState = {
        "messages": [],
        "session_id": session_id,
        "user_input": message,
        "user_id": user_id,
        "channel": channel,
        "clarify_count": session.clarify_count,
        "clarify_history": [],
        "router_result": None,
        "router_trace": [],
        "rag_context": [],
        "tool_calls": [],
        "tool_results": [],
        "final_response": None,
        "should_transfer_human": False,
        "fallback_level": 0,
        "error_history": [],
        "trace_id": trace_id,
    }

    try:
        # Run the agent graph
        result = await agent_graph.ainvoke(initial_state)

        final_response = result.get("final_response")
        if final_response is None:
            final_response = AgentResponse(
                text="很抱歉，系统处理您的请求时遇到了问题，请稍后再试。",
                action="reply",
                metadata={"trace_id": trace_id},
            ).model_dump()

        logger.info("chat.response", session_id=session_id, action=final_response.get("action"), trace_id=trace_id)

        return ChatResponse(response=AgentResponse(**final_response))

    except Exception as e:
        logger.error("chat.error", session_id=session_id, error=str(e), trace_id=trace_id)
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{str(e)}")


# ── Session History API ─────────────────────────────────────────


@router.get("/sessions")
async def list_sessions():
    """List all saved sessions."""
    sessions = session_store.list_sessions()
    return {
        "sessions": [
            {
                "id": s["id"],
                "title": s["title"] or "新对话",
                "msg_count": s.get("msg_count", 0),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
            }
            for s in sessions
            if s.get("msg_count", 0) > 0  # Only show sessions with messages
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get full message history for a session."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = session_store.get_messages(session_id, token_limit=999999)
    return {
        "session": {
            "id": session["id"],
            "title": session["title"] or "新对话",
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
        },
        "messages": [
            {"role": m["role"], "content": m["content"], "created_at": m.get("created_at", "")}
            for m in messages
        ],
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its messages."""
    session_store.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}
