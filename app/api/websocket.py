from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.state import AgentState
from app.agent.graph import agent_graph
from app.core.di import get_session_manager
from app.core.observability import generate_trace_id, set_trace_id, set_session_id, get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/api/v1/chat/stream")
async def chat_stream(websocket: WebSocket):
    await websocket.accept()

    session_id = ""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        # Wait for first message with session_id
        data = await websocket.receive_text()
        init_msg = json.loads(data)
        session_id = init_msg.get("session_id", "")
        set_session_id(session_id)

        logger.info("ws.connected", session_id=session_id, trace_id=trace_id)

        session_mgr = get_session_manager()
        await session_mgr.get_or_create(session_id)

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            message = msg.get("message", "").strip()

            if not message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            trace_id = generate_trace_id()
            set_trace_id(trace_id)

            initial_state: AgentState = {
                "messages": [],
                "session_id": session_id,
                "user_input": message,
                "user_id": msg.get("user_id", ""),
                "channel": msg.get("channel", "web"),
                "clarify_count": 0,
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

            # Stream progress events
            await websocket.send_json({"type": "status", "status": "processing", "trace_id": trace_id})

            result = await agent_graph.ainvoke(initial_state)

            final_response = result.get("final_response")
            if final_response:
                await websocket.send_json({"type": "response", "data": final_response, "trace_id": trace_id})
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "No response generated",
                    "trace_id": trace_id,
                })

    except WebSocketDisconnect:
        logger.info("ws.disconnected", session_id=session_id)
    except Exception as e:
        logger.error("ws.error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e), "trace_id": trace_id})
        except Exception:
            pass
