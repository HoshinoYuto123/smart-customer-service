from __future__ import annotations

import json
import re

from app.agent.state import AgentState
from app.agent.types import Message, RouteDecision
from app.core.di import get_llm_provider, get_session_manager
from app.core.observability import get_logger, get_trace_id
from app.prompts.manager import prompt_manager

logger = get_logger(__name__)

# Layer 1: keyword-based coarse routing
_DOMAIN_KEYWORDS = {
    "account": ["账户", "账号", "登录", "注册", "密码", "认证", "绑定", "手机号", "邮箱", "注销", "安全",
                "实名", "验证码", "人脸", "冻结", "解封"],
    "payment": ["支付", "付款", "退款", "缴费", "充值", "余额", "账单", "发票", "优惠券", "代金券",
                "银行卡", "信用卡", "花呗", "分期", "免密支付", "扣款"],
    "order": ["订单", "发货", "物流", "快递", "收货", "配送", "自提", "签收", "下单", "购物车",
              "限购", "预售", "缺货", "改地址", "修改订单", "取消订单"],
    "after_sale": ["退货", "换货", "售后", "投诉", "维权", "保修", "维修", "赔偿", "差评", "纠纷",
                   "质量", "假货", "破损", "退差价", "补发"],
}


def _infer_tools(user_input: str, domain: str) -> list[str]:
    """Choose safe deterministic tools when the model did not return a plan."""
    tools = ["faq_search"]
    if any(word in user_input for word in ["政策", "规则", "时效", "积分"]):
        tools.append("policy_search")
    if domain == "order" and (
        re.search(r"ORD\d{6,}|1[3-9]\d{9}", user_input, re.IGNORECASE)
        or any(word in user_input for word in ["查询", "查一下", "物流", "快递到", "订单状态"])
    ):
        tools.append("query_order")
    if domain == "account" and (
        re.search(r"U\d{6,}|1[3-9]\d{9}", user_input, re.IGNORECASE)
        and any(word in user_input for word in ["查询", "余额", "积分", "会员", "账户状态"])
    ):
        tools.append("query_account")
    if any(word in user_input for word in ["创建工单", "提交工单", "生成工单"]):
        tools.append("create_ticket")
    if any(word in user_input for word in ["转人工", "人工客服", "人工处理"]):
        tools.append("transfer_human")
    return list(dict.fromkeys(tools))


def _layer1_coarse_router(user_input: str) -> dict[str, float]:
    """Layer 1: Fast keyword-based coarse classification."""
    import re
    scores = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in user_input)
        scores[domain] = min(matches * 0.35, 1.0)
    # Boost: order ID pattern (ORD + digits) strongly indicates order domain
    if re.search(r'ORD\d{6,}', user_input, re.IGNORECASE):
        scores["order"] = max(scores.get("order", 0), 0.9)
    # Boost: phone number pattern
    if re.search(r'1[3-9]\d{9}', user_input):
        scores["account"] = max(scores.get("account", 0), 0.5)
        scores["order"] = max(scores.get("order", 0), 0.5)
    return scores


async def _layer2_summary_router(user_input: str, domain_scores: dict[str, float]) -> list[dict]:
    """Layer 2: attach curated domain summaries to ranked rule candidates."""
    try:
        from app.rag.knowledge_base import knowledge_base_manager

        candidates = []
        domains = sorted(domain_scores, key=domain_scores.get, reverse=True)

        for domain in domains:
            if domain_scores[domain] > 0:
                summary = knowledge_base_manager.get_domain_summary(domain)
                candidates.append({
                    "domain": domain,
                    "score": domain_scores[domain],
                    "summary": summary[:500],
                })

        # If no keyword match, try all domains
        if not candidates:
            for domain in ["account", "payment", "order", "after_sale"]:
                summary = knowledge_base_manager.get_domain_summary(domain)
                candidates.append({
                    "domain": domain,
                    "score": 0.1,
                    "summary": summary[:500],
                })

        return candidates
    except Exception as e:
        logger.warning("rag_router.fallback", error=str(e))
        return [{"domain": d, "score": s, "summary": d} for d, s in domain_scores.items()]


async def router_node(state: AgentState) -> dict:
    """Three-layer routing: coarse rules -> domain summaries -> LLM fine routing."""
    user_input = state.get("user_input", "")
    session_id = state.get("session_id", "")
    trace_id = get_trace_id()

    logger.info("router.start", input_length=len(user_input), trace_id=trace_id)

    # Layer 1: Coarse keyword routing
    domain_scores = _layer1_coarse_router(user_input)
    logger.info("router.layer1", scores=domain_scores)

    # Layer 2: enrich candidates with curated domain summaries
    candidates = await _layer2_summary_router(user_input, domain_scores)
    logger.info("router.layer2", domains=[c["domain"] for c in candidates])

    # Layer 3: LLM fine routing (only if multiple candidates or low confidence)
    best_domain = max(domain_scores, key=domain_scores.get) if domain_scores else "global"
    best_score = domain_scores.get(best_domain, 0)

    if best_score > 0.3 and len([c for c in candidates if c["score"] > 0.3]) <= 1:
        # High confidence single domain - skip LLM
        route_decision = RouteDecision(
            domain=best_domain,
            sub_intent="",
            confidence=best_score,
            suggested_tools=_infer_tools(user_input, best_domain),
            reasoning=f"关键词匹配: {best_domain}",
            layer1_result=best_domain,
            layer2_candidates=candidates,
        )
        logger.info("router.skip_llm", domain=best_domain, confidence=best_score)
    else:
        # Use LLM for fine routing
        route_decision = await _layer3_llm_router(user_input, candidates, session_id)

    # Ensure a conservative deterministic plan exists without executing every
    # tool associated with a domain.
    default_tools = _infer_tools(user_input, route_decision.domain)
    existing = set(route_decision.suggested_tools)
    for t in default_tools:
        if t not in existing:
            route_decision.suggested_tools.append(t)

    logger.info("router.decision", domain=route_decision.domain, confidence=route_decision.confidence)

    return {
        "router_result": route_decision.model_dump(),
        "tool_plan": route_decision.tool_plan,
        "router_trace": [
            {"layer": "coarse", "scores": domain_scores},
            {"layer": "rag", "candidates": candidates},
            {"layer": "llm", "domain": route_decision.domain, "confidence": route_decision.confidence},
        ],
    }


async def _layer3_llm_router(user_input: str, candidates: list[dict], session_id: str) -> RouteDecision:
    """Layer 3: LLM-based fine routing with domain summaries."""
    try:
        provider = get_llm_provider("router")

        domain_summaries = "\n\n".join(
            f"## {c['domain']}\n{c['summary']}" for c in candidates
        )

        # Get available tools
        from app.tools.registry import tool_registry
        available_tools = "\n".join(
            f"- {t['definition'].name}: {t['definition'].description}"
            for t in tool_registry.list_all()
        )

        prompt = prompt_manager.render("router_prompt", {})

        messages = [
            Message(role="system", content=prompt),
            Message(
                role="user",
                content=(
                    f"<domain_summaries>\n{domain_summaries}\n</domain_summaries>\n\n"
                    f"<available_tools>\n{available_tools}\n</available_tools>\n\n"
                    f"<user_question>\n{user_input}\n</user_question>"
                ),
            ),
        ]

        # Get tool definitions for function calling
        tools = tool_registry.get_tools_by_domain("global") + tool_registry.get_tools_by_domain(candidates[0]["domain"] if candidates else "global")
        tool_defs = [t["definition"] for t in tools[:5]]

        response = await provider.chat_with_tools(messages, tools=tool_defs, temperature=0.3, max_tokens=512)

        decision = _parse_route_response(response.content, candidates)
        if response.tool_calls:
            decision.tool_plan = [
                {"tool": call.get("name", ""), "params": call.get("args", {})}
                for call in response.tool_calls
                if call.get("name")
            ]
            decision.suggested_tools = [item["tool"] for item in decision.tool_plan]
        return decision

    except Exception as e:
        logger.error("router.llm_error", error=str(e))
        # Fallback to first candidate
        if candidates:
            return RouteDecision(
                domain=candidates[0]["domain"],
                confidence=0.3,
                reasoning=f"LLM路由失败，回退到最佳候选: {e}",
                layer2_candidates=candidates,
            )
        return RouteDecision(domain="global", confidence=0.1, reasoning="路由失败，使用全局域")


def _parse_route_response(content: str, candidates: list[dict]) -> RouteDecision:
    try:
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group())
            return RouteDecision(
                domain=data.get("domain", candidates[0]["domain"] if candidates else "global"),
                sub_intent=data.get("sub_intent", ""),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                suggested_tools=data.get("suggested_tools", []),
                layer2_candidates=candidates,
            )
    except (json.JSONDecodeError, Exception):
        pass

    return RouteDecision(
        domain=candidates[0]["domain"] if candidates else "global",
        confidence=0.4,
        reasoning="从回复中解析路由失败",
        layer2_candidates=candidates,
    )
