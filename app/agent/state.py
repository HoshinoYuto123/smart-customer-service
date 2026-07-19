from typing import TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    messages: list[BaseMessage]
    session_id: str
    user_input: str
    user_id: str
    channel: str
    current_domain: str
    clarify_count: int
    clarify_history: list[dict]
    router_result: dict | None
    router_trace: list[dict]
    rag_context: list[dict]
    tool_calls: list[dict]
    tool_plan: list[dict]
    tool_results: list[dict]
    final_response: dict | None
    should_transfer_human: bool
    fallback_level: int
    error_history: list[dict]
    trace_id: str
