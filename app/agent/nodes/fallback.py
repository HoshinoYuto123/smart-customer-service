from __future__ import annotations

from app.agent.state import AgentState
from app.agent.types import AgentResponse
from app.core.observability import get_logger, get_trace_id
from app.core.config import get_app_config

logger = get_logger(__name__)


async def fallback_node(state: AgentState) -> dict:
    """Execute fallback chain: rule-based reply -> queue -> human transfer."""
    fallback_level = state.get("fallback_level", 0)
    clarify_count = state.get("clarify_count", 0)
    error_history = state.get("error_history", [])
    trace_id = get_trace_id()

    logger.info("fallback.start", level=fallback_level, errors=len(error_history), trace_id=trace_id)

    # Level 0: Clarification exhausted -> transfer to human
    if clarify_count >= get_app_config().agent.max_clarify_rounds:
        response = AgentResponse(
            text="抱歉，我暂时无法准确理解您的问题。正在为您转接人工客服，请稍等。",
            multimedia=[],
            quick_replies=[{"label": "继续等待", "value": "wait", "action": ""}],
            action="transfer_human",
            metadata={"trace_id": trace_id, "fallback_level": fallback_level, "reason": "clarify_exhausted"},
        )
        return {
            "final_response": response.model_dump(),
            "should_transfer_human": True,
            "fallback_level": fallback_level + 1,
        }

    # Level 1: Use RAG-only response without LLM generation
    if fallback_level <= 1:
        rag_context = state.get("rag_context", [])
        if rag_context:
            top = rag_context[0]
            text = f"以下是根据知识库为您找到的相关信息：\n\n{top.get('answer', '')}\n\n如果未能解决您的问题，可以联系人工客服。"
        else:
            text = "很抱歉，当前系统繁忙，无法为您生成智能回复。请稍后再试或联系人工客服。"

        response = AgentResponse(
            text=text,
            multimedia=[],
            quick_replies=[
                {"label": "联系人工客服", "value": "转人工", "action": "transfer_human"},
                {"label": "重新提问", "value": "restart", "action": ""},
            ],
            action="reply",
            metadata={"trace_id": trace_id, "fallback_level": fallback_level, "reason": "llm_unavailable"},
        )
        return {
            "final_response": response.model_dump(),
            "fallback_level": fallback_level + 1,
        }

    # Level 2+: Queue or transfer to human
    if fallback_level >= 2:
        response = AgentResponse(
            text="很抱歉，当前所有服务通道繁忙。已为您创建工单，客服人员将在工作时间尽快与您联系。感谢您的耐心等待！",
            multimedia=[],
            quick_replies=[{"label": "查看工单", "value": "view_ticket", "action": "create_ticket"}],
            action="create_ticket",
            metadata={"trace_id": trace_id, "fallback_level": fallback_level, "reason": "all_channels_exhausted"},
        )
        return {
            "final_response": response.model_dump(),
            "should_transfer_human": True,
            "fallback_level": fallback_level + 1,
        }

    return {"fallback_level": fallback_level + 1}
