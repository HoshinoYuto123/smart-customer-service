from __future__ import annotations

import asyncio
import re

from app.agent.state import AgentState
from app.agent.types import Message, ToolResult
from app.core.config import get_app_config
from app.core.observability import get_logger, get_trace_id

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
    error_history = list(state.get("error_history", []))
    tool_plan = state.get("tool_plan", [])
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
    planned_params = {item.get("tool"): item.get("params", {}) for item in tool_plan}

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
            params = planned_params.get(tool_name) or _build_tool_params(
                tool_name,
                user_input=user_input,
                domain=domain,
                user_id=state.get("user_id", ""),
            )
            result = await tool_registry.execute(tool_name, params)
            new_tool_calls.append({"tool": tool_name, "params": params})
            new_tool_results.append(result.model_dump())
            if not result.success and result.error_message:
                error_history.append({"source": tool_name, "error": result.error_message})
            logger.info("executor.tool_done", tool=tool_name, success=result.success)
        except Exception as e:
            logger.error("executor.tool_error", tool=tool_name, error=str(e))
            new_tool_results.append(ToolResult(
                tool_name=tool_name,
                success=False,
                error_message=str(e),
            ).model_dump())
            error_history.append({"source": tool_name, "error": str(e)})

    return {
        "rag_context": rag_context,
        "tool_calls": new_tool_calls,
        "tool_results": new_tool_results,
        "error_history": error_history,
    }


def _build_tool_params(tool_name: str, *, user_input: str, domain: str, user_id: str) -> dict:
    """Create schema-shaped deterministic parameters for non-LLM plans."""
    if tool_name in {"faq_search", "policy_search"}:
        params = {"query": user_input}
        if tool_name == "faq_search":
            params["domain"] = domain
        return params
    if tool_name == "query_order":
        params: dict[str, str] = {"query": user_input}
        order_match = re.search(r"ORD\d{6,}", user_input, re.IGNORECASE)
        phone_match = re.search(r"1[3-9]\d{9}", user_input)
        if order_match:
            params["order_id"] = order_match.group(0)
        if phone_match:
            params["phone"] = phone_match.group(0)
        return params
    if tool_name == "query_account":
        params = {"user_id": user_id}
        phone_match = re.search(r"1[3-9]\d{9}", user_input)
        if phone_match:
            params["phone"] = phone_match.group(0)
        return params
    if tool_name == "create_ticket":
        category = {
            "order": "订单问题",
            "account": "账户问题",
            "payment": "退款申请",
            "after_sale": "投诉建议",
        }.get(domain, "其他")
        return {
            "title": user_input[:40] or "用户问题",
            "description": user_input,
            "priority": "中",
            "category": category,
        }
    if tool_name == "transfer_human":
        return {"reason": "用户主动要求转人工", "summary": user_input}
    return {}


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

        try:
            reranked = await asyncio.wait_for(
                reranker.rerank(query, candidates, top_k=5),
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("rag.reranker_fallback", error=str(exc)[:100])
            reranked = candidates[:5]
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
