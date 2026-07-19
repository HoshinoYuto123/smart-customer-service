from __future__ import annotations

import json
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.service import run_agent_turn
from app.core.di import get_session_manager
from app.core.observability import generate_trace_id, set_trace_id, set_session_id, get_logger
from app.core.auth import get_websocket_principal

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/api/v1/chat/stream")
async def chat_stream(websocket: WebSocket):
    try:
        principal = get_websocket_principal(websocket)
    except Exception:
        await websocket.close(code=4401, reason="Unauthorized")
        return
    await websocket.accept()

    session_id = ""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        # Wait for first message with session_id
        data = await websocket.receive_text()
        init_msg = json.loads(data)
        session_id = init_msg.get("session_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
            await websocket.close(code=1008, reason="Invalid session_id")
            return
        set_session_id(session_id)

        logger.info("ws.connected", session_id=session_id, trace_id=trace_id)

        session_mgr = get_session_manager()
        await session_mgr.get_or_create(session_id, user_id=principal.user_id)

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            message = msg.get("message", "").strip()

            if not message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue
            if len(message) > 10000:
                await websocket.send_json({"type": "error", "message": "Message too long"})
                continue

            trace_id = generate_trace_id()
            set_trace_id(trace_id)

            # Stream progress events
            await websocket.send_json({"type": "status", "status": "processing", "trace_id": trace_id})
            async with session_mgr.turn_lock(session_id):
                session = await session_mgr.get_or_create(session_id, user_id=principal.user_id)
                response = await run_agent_turn(
                    session_manager=session_mgr,
                    session=session,
                    message=message,
                    user_id=principal.user_id,
                    channel=msg.get("channel", "web"),
                    trace_id=trace_id,
                )
            await websocket.send_json({"type": "response", "data": response.model_dump(), "trace_id": trace_id})

    except WebSocketDisconnect:
        logger.info("ws.disconnected", session_id=session_id)
    except Exception as e:
        logger.error("ws.error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": "请求处理失败，请提供追踪编号", "trace_id": trace_id})
        except Exception:
            pass
