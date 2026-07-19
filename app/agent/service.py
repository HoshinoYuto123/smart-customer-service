"""Application service for running and persisting one agent turn."""

from __future__ import annotations

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.agent.types import AgentResponse, SessionContext
from app.core.session import SessionManager


async def run_agent_turn(
    *,
    session_manager: SessionManager,
    session: SessionContext,
    message: str,
    user_id: str,
    channel: str,
    trace_id: str,
) -> AgentResponse:
    initial_state: AgentState = {
        "messages": [],
        "session_id": session.session_id,
        "user_input": message,
        "user_id": user_id,
        "channel": channel,
        "current_domain": session.current_domain,
        "clarify_count": session.clarify_count,
        "clarify_history": [],
        "router_result": None,
        "router_trace": [],
        "rag_context": [],
        "tool_calls": [],
        "tool_plan": [],
        "tool_results": [],
        "final_response": None,
        "should_transfer_human": False,
        "fallback_level": 0,
        "error_history": [],
        "trace_id": trace_id,
    }

    result = await agent_graph.ainvoke(initial_state)
    final_data = result.get("final_response") or AgentResponse(
        text="很抱歉，系统处理您的请求时遇到了问题，请稍后再试。",
        action="reply",
        metadata={"trace_id": trace_id, "fallback": True},
    ).model_dump()
    response = AgentResponse(**final_data)

    await session_manager.record_turn(
        session.session_id,
        user_content=message,
        assistant_content=response.text,
        clarify_count=int(result.get("clarify_count", session.clarify_count)),
        current_domain=(result.get("router_result") or {}).get("domain", session.current_domain),
    )
    return response
