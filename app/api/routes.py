from __future__ import annotations

import asyncio
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.agent.types import ChatRequest, ChatResponse, HealthResponse
from app.agent.service import run_agent_turn
from app.core import session_store
from app.core.di import get_session_manager
from app.core.observability import set_trace_id, set_session_id, generate_trace_id, get_logger
from app.core.config import get_model_config, get_app_config
from app.core.auth import COOKIE_NAME, Principal, get_request_principal, issue_token, set_auth_cookie, verify_token

router = APIRouter(prefix="/api/v1")
logger = get_logger(__name__)


@router.post("/auth/anonymous")
async def create_anonymous_identity(request: Request, response: Response):
    """Issue an HttpOnly signed identity cookie for the web client."""
    existing = request.cookies.get(COOKIE_NAME, "")
    if existing:
        try:
            principal = verify_token(existing)
            return {"user_id": principal.user_id}
        except HTTPException:
            pass
    token, principal = issue_token()
    set_auth_cookie(response, token)
    return {"user_id": principal.user_id}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    snapshot = await _health_snapshot()
    if snapshot.checks.get("session_store"):
        snapshot.status = "ok"
    return snapshot


@router.get("/health/live")
async def liveness_check():
    return {"status": "ok"}


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(response: Response):
    snapshot = await _health_snapshot()
    if snapshot.status != "ok":
        response.status_code = 503
    return snapshot


async def _health_snapshot() -> HealthResponse:
    config = get_model_config()
    app_config = get_app_config()
    checks = {"session_store": False, "knowledge_index": False, "provider_config": False}
    try:
        await asyncio.to_thread(session_store.init_db)
        checks["session_store"] = True
    except Exception:
        pass
    try:
        checks["knowledge_index"] = await asyncio.to_thread(_get_health_indexer().collection_count) > 0
    except Exception:
        pass
    selected = config.routing.answer
    checks["provider_config"] = bool(config.providers.get(selected) and config.providers[selected].api_key)
    ready = checks["session_store"] and checks["knowledge_index"] and (
        checks["provider_config"] or app_config.app.mode == "demo"
    )
    return HealthResponse(
        status="ok" if ready else "degraded",
        version=app_config.app.version,
        providers=list(config.providers.keys()),
        mode=app_config.app.mode,
        checks=checks,
    )


@lru_cache()
def _get_health_indexer():
    from app.rag.indexer import Indexer
    return Indexer()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, principal: Principal = Depends(get_request_principal)):
    session_id = request.session_id
    message = request.message.strip()
    user_id = principal.user_id
    channel = request.context.get("channel", "web")
    trace_id = generate_trace_id()

    set_trace_id(trace_id)
    set_session_id(session_id)

    if not message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    logger.info("chat.request", session_id=session_id, message_length=len(message), trace_id=trace_id)

    session_mgr = get_session_manager()
    try:
        async with session_mgr.turn_lock(session_id):
            try:
                session = await session_mgr.get_or_create(session_id, user_id=user_id, channel=channel)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail="无权访问该会话") from exc
            response = await run_agent_turn(
                session_manager=session_mgr,
                session=session,
                message=message,
                user_id=user_id,
                channel=channel,
                trace_id=trace_id,
            )
        logger.info("chat.response", session_id=session_id, action=response.action, trace_id=trace_id)
        return ChatResponse(response=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat.error", session_id=session_id, error=str(e), trace_id=trace_id)
        raise HTTPException(status_code=500, detail=f"Agent 执行失败，请提供追踪编号：{trace_id}")


# ── Session History API ─────────────────────────────────────────


@router.get("/sessions")
async def list_sessions(principal: Principal = Depends(get_request_principal)):
    """List all saved sessions."""
    sessions = await asyncio.to_thread(session_store.list_sessions, principal.user_id)
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
async def get_session_detail(session_id: str, principal: Principal = Depends(get_request_principal)):
    """Get full message history for a session."""
    session = await asyncio.to_thread(session_store.get_session, session_id, principal.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await asyncio.to_thread(session_store.get_messages, session_id, 999999)
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
async def delete_session(session_id: str, principal: Principal = Depends(get_request_principal)):
    """Delete a session and its messages."""
    if not await asyncio.to_thread(session_store.delete_session, session_id, principal.user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "deleted", "session_id": session_id}
