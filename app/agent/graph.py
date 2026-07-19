from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.nodes.clarify import clarify_node
from app.agent.nodes.router import router_node
from app.agent.nodes.executor import executor_node
from app.agent.nodes.respond import respond_node
from app.agent.nodes.fallback import fallback_node
from app.core.config import get_app_config


def route_after_clarify(state: AgentState) -> str:
    """Decide next step after clarification evaluation."""
    final_response = state.get("final_response")
    if final_response and final_response.get("action") == "clarify":
        return "clarify_response"
    clarify_count = state.get("clarify_count", 0)
    if clarify_count >= get_app_config().agent.max_clarify_rounds:
        return "give_up"
    return "ready"


def route_after_execute(state: AgentState) -> str:
    """Decide whether to loop for more tools or proceed to response."""
    # Check for errors
    error_history = state.get("error_history", [])
    if len(error_history) >= 3:
        return "error"

    # Single pass: always go to respond after executor
    # (the executor node runs all needed tools in one pass)
    return "ready"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph state machine for the SCS Agent."""

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("clarify", clarify_node)
    graph.add_node("router", router_node)
    graph.add_node("executor", executor_node)
    graph.add_node("respond", respond_node)
    graph.add_node("fallback", fallback_node)

    # Entry point
    graph.set_entry_point("clarify")

    # Conditional edges after clarify
    graph.add_conditional_edges(
        "clarify",
        route_after_clarify,
        {
            "clarify_response": "respond",  # Go to respond with clarification message
            "ready": "router",
            "give_up": "fallback",
        },
    )

    # Router always goes to executor
    graph.add_edge("router", "executor")

    # Conditional edges after executor
    graph.add_conditional_edges(
        "executor",
        route_after_execute,
        {
            "need_more_tools": "executor",  # Loop back for more tools
            "ready": "respond",
            "error": "fallback",
        },
    )

    # Respond and fallback are terminal
    graph.add_edge("respond", END)
    graph.add_edge("fallback", END)

    return graph.compile()


# Singleton compiled graph
agent_graph = build_graph()
