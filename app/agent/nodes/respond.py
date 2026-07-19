from __future__ import annotations

import json
import re

from app.agent.state import AgentState
from app.agent.types import Message, AgentResponse
from app.core.di import get_llm_provider, get_session_manager
from app.core.observability import get_logger, get_trace_id
from app.prompts.manager import prompt_manager

logger = get_logger(__name__)


def _extract_text(content: str) -> str:
    """Extract plain text from LLM response, handling JSON-formatted outputs."""
    content = content.strip()
    # If it looks like JSON, try to extract the "text" field
    if content.startswith("{") and content.endswith("}"):
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "text" in data:
                return data["text"]
        except (json.JSONDecodeError, TypeError):
            pass
    # Try to find JSON block inside markdown
    json_match = re.search(r'\{[^{}]*"text"\s*:\s*"[^"]*"[^{}]*\}', content)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict) and "text" in data:
                return data["text"]
        except (json.JSONDecodeError, TypeError):
            pass
    return content


async def respond_node(state: AgentState) -> dict:
    """Generate the final response using RAG context and tool results."""
    user_input = state.get("user_input", "")
    session_id = state.get("session_id", "")
    router_result = state.get("router_result", {})
    rag_context = state.get("rag_context", [])
    tool_results = state.get("tool_results", [])
    trace_id = get_trace_id()

    # If clarification response was already generated, return it directly
    existing_response = state.get("final_response")
    if existing_response and existing_response.get("action") == "clarify":
        return {}

    domain = router_result.get("domain", "global") if router_result else "global"

    logger.info("respond.start", domain=domain, rag_count=len(rag_context), trace_id=trace_id)

    # Build context from RAG results
    rag_text = ""
    if rag_context:
        rag_text = "\n\n".join(
            f"**相关知识 {i+1}** (匹配度: {r.get('score', 0):.2f})\n问题: {r.get('question', '')}\n答案: {r.get('answer', '')}"
            for i, r in enumerate(rag_context[:5])
        )

    # Build context from tool results
    tool_text = ""
    if tool_results:
        parts = []
        for r in tool_results:
            data = r.get("data", {})
            # Use pre-formatted summary if available
            if isinstance(data, dict) and data.get("summary_text"):
                parts.append(data["summary_text"])
            elif r.get("success"):
                parts.append(f"- {r.get('tool_name', '')}: {data}")
            else:
                parts.append(f"- {r.get('tool_name', '')}: 失败 - {r.get('error_message', '')}")
        tool_text = "\n".join(parts)

    try:
        provider = get_llm_provider("answer")
        session_mgr = get_session_manager()
        chat_history = await session_mgr.get_history(session_id)
        history_str = "\n".join(
            f"{h['role']}: {h['content']}" for h in chat_history[-6:]
        )

        prompt = prompt_manager.render("answer_prompt", {"domain": domain})
        user_payload = (
            f"<conversation_history>\n{history_str}\n</conversation_history>\n\n"
            f"<knowledge_base>\n{rag_text or '无相关知识库结果'}\n</knowledge_base>\n\n"
            f"<tool_results>\n{tool_text or '无工具查询结果'}\n</tool_results>\n\n"
            f"<user_question>\n{user_input}\n</user_question>"
        )

        messages = [
            Message(role="system", content=prompt),
            Message(role="user", content=user_payload),
        ]

        response = await provider.chat(messages, temperature=0.7, max_tokens=1024)

        # Try to extract plain text if LLM returned JSON
        reply_text = _extract_text(response.content)

        # Build quick replies based on domain
        quick_replies = _get_domain_quick_replies(domain)

        agent_response = AgentResponse(
            text=reply_text,
            multimedia=[],
            quick_replies=quick_replies,
            action="reply",
            metadata={
                "trace_id": trace_id,
                "router_domain": domain,
                "rag_sources": [r.get("id", "") for r in rag_context],
                "model": response.model,
                "tokens_used": response.tokens_used,
                "latency_ms": response.latency_ms,
            },
        )

        logger.info("respond.done", domain=domain, tokens=response.tokens_used)

        return {"final_response": agent_response.model_dump()}

    except Exception as e:
        logger.error("respond.error", error=str(e))
        # Generate fallback: prefer tool results over generic message
        fallback_text = _generate_fallback_with_tools(tool_results, rag_context, domain)

        agent_response = AgentResponse(
            text=fallback_text,
            multimedia=[],
            quick_replies=[{"label": "联系人工客服", "value": "转人工", "action": "transfer_human"}],
            action="reply",
            metadata={"trace_id": trace_id, "router_domain": domain, "fallback": True},
        )

        return {"final_response": agent_response.model_dump()}


def _get_domain_quick_replies(domain: str) -> list:
    replies = {
        "account": [
            {"label": "修改密码", "value": "如何修改密码", "action": ""},
            {"label": "账户安全", "value": "账户安全设置", "action": ""},
            {"label": "联系人工", "value": "转人工", "action": "transfer_human"},
        ],
        "payment": [
            {"label": "退款进度", "value": "退款进度查询", "action": ""},
            {"label": "支付方式", "value": "支持哪些支付方式", "action": ""},
            {"label": "联系人工", "value": "转人工", "action": "transfer_human"},
        ],
        "order": [
            {"label": "物流查询", "value": "物流查询", "action": ""},
            {"label": "修改订单", "value": "如何修改订单", "action": ""},
            {"label": "联系人工", "value": "转人工", "action": "transfer_human"},
        ],
        "after_sale": [
            {"label": "申请退货", "value": "如何申请退货", "action": ""},
            {"label": "投诉建议", "value": "我要投诉", "action": ""},
            {"label": "联系人工", "value": "转人工", "action": "transfer_human"},
        ],
    }
    return replies.get(domain, replies["order"])


def _generate_simple_response(rag_context: list[dict], domain: str) -> str:
    """Generate a simple response from RAG context without LLM."""
    if rag_context:
        top = rag_context[0]
        return f"根据我们的知识库，以下是相关信息：\n\n{top.get('answer', '请查看帮助中心获取更多信息。')}"
    return "很抱歉，我暂时无法处理您的请求。已为您记录问题，客服稍后会联系您。"


def _generate_fallback_with_tools(tool_results: list[dict], rag_context: list[dict], domain: str) -> str:
    """Generate fallback response prioritizing tool query results."""
    # Check tool results for useful data
    if tool_results:
        for tr in tool_results:
            if not tr.get("success"):
                continue
            data = tr.get("data", {})
            if isinstance(data, dict) and data.get("summary_text"):
                return f"已为您查询到以下信息（AI回复暂不可用，直接展示原始数据）：\n\n{data['summary_text']}"
            if isinstance(data, dict) and data.get("orders"):
                orders = data["orders"]
                lines = [f"找到 {len(orders)} 笔订单："]
                for o in orders:
                    lines.append(f"\n订单号: {o.get('order_id', '')}")
                    lines.append(f"商品: {o.get('product', '')}")
                    lines.append(f"状态: {o.get('status', '')}")
                    lines.append(f"物流: {o.get('logistics_company', '未知')}")
                    if o.get("tracking_number"):
                        lines.append(f"快递单号: {o['tracking_number']}")
                return "\n".join(lines)

    # Fall back to RAG context
    if rag_context:
        top = rag_context[0]
        return f"根据知识库，以下是相关信息：\n\n{top.get('answer', '请查看帮助中心获取更多信息。')}"

    return "很抱歉，当前AI服务暂时不可用，已为您记录问题，客服稍后会联系您。"
