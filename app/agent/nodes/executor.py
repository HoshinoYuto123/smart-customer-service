from __future__ import annotations

import asyncio

from app.agent.state import AgentState
from app.agent.types import Message, ToolResult
from app.core.config import get_app_config
from app.core.di import get_llm_provider
from app.core.observability import get_logger, get_trace_id, log_execution

logger = get_logger(__name__)


async def executor_node(state: AgentState) -> dict:
    """Execute RAG retrieval and tool calls based on router decision."""
    user_input = state.get("user_input", "")
    router_result = state.get("router_result", {})
    domain = router_result.get("domain", "global") if router_result else "global"
    suggested_tools = router_result.get("suggested_tools", []) if router_result else []
    trace_id = get_trace_id()

    logger.info("executor.start", domain=domain, suggested_tools=suggested_tools, trace_id=trace_id)

    config = get_app_config()
    max_rounds = config.agent.max_tool_call_rounds
    tool_calls_made = state.get("tool_calls", [])
    tool_results = state.get("tool_results", [])
    rag_context = state.get("rag_context", [])

    # Round 1: Always do RAG retrieval
    if not rag_context:
        rag_results = await _do_rag_search(user_input, domain)
        rag_context = rag_results

    # Check if tools are needed
    if not suggested_tools and len(tool_calls_made) >= max_rounds:
        logger.info("executor.done", rag_count=len(rag_context), tool_count=len(tool_results))
        return {
            "rag_context": rag_context,
            "tool_calls": tool_calls_made,
            "tool_results": tool_results,
        }

    # Execute suggested tools
    from app.tools.registry import tool_registry

    new_tool_results = list(tool_results)
    new_tool_calls = list(tool_calls_made)

    tools_to_run = suggested_tools[:3] if suggested_tools else ["faq_search"]

    # Only run tools we haven't run yet
    already_run = {c["tool"] for c in new_tool_calls}
    tools_to_run = [t for t in tools_to_run if t not in already_run]

    for tool_name in tools_to_run:
        if len(new_tool_calls) >= max_rounds:
            break

        tool = tool_registry.get_tool(tool_name)
        if not tool:
            continue

        try:
            params = {"query": user_input, "domain": domain}
            result = await tool_registry.execute(tool_name, params)
            new_tool_calls.append({"tool": tool_name, "params": params})
            new_tool_results.append(result.model_dump())
            logger.info("executor.tool_done", tool=tool_name, success=result.success)
        except Exception as e:
            logger.error("executor.tool_error", tool=tool_name, error=str(e))
            new_tool_results.append(ToolResult(
                tool_name=tool_name,
                success=False,
                error_message=str(e),
            ).model_dump())

    return {
        "rag_context": rag_context,
        "tool_calls": new_tool_calls,
        "tool_results": new_tool_results,
    }


async def _do_rag_search(query: str, domain: str | None = None) -> list[dict]:
    """Perform hybrid RAG search with timeout to avoid blocking on model download."""
    try:
        from app.rag.retriever import hybrid_retriever
        from app.rag.reranker import reranker

        # Timeout after 5 seconds to avoid blocking on model downloads
        candidates = await asyncio.wait_for(
            hybrid_retriever.retrieve(query, domain=domain, top_k=20),
            timeout=5.0,
        )
        if not candidates:
            return []

        reranked = await asyncio.wait_for(
            reranker.rerank(query, candidates, top_k=5),
            timeout=5.0,
        )
        return [
            {
                "id": r.get("id", ""),
                "domain": r.get("domain", ""),
                "question": r.get("question", ""),
                "answer": r.get("answer", ""),
                "score": r.get("rerank_score", r.get("score", 0)),
            }
            for r in reranked
        ]
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("rag.search_fallback", error=str(e)[:100])
        return []
