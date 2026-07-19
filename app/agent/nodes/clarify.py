from __future__ import annotations

import json
import re

from app.agent.state import AgentState
from app.agent.types import ClarifyResult, Message
from app.core.config import get_app_config
from app.core.di import get_llm_provider, get_session_manager
from app.core.observability import get_logger, get_trace_id
from app.prompts.manager import prompt_manager

logger = get_logger(__name__)


def _quick_fuzz_check(text: str) -> float:
    """Fast heuristic fuzziness score without LLM."""
    text = text.strip()
    score = 1.0
    if len(text) < 5:
        score -= 0.3
    if len(text) < 10:
        score -= 0.15
    vague_words = ["那个", "这个", "不好用", "怎么弄", "咋回事", "不行", "出问题了", "帮我", "看看"]
    if any(w in text for w in vague_words):
        score -= 0.25
    # Penalize lack of specific nouns/keywords
    specific_indicators = ["订单", "支付", "退款", "账户", "密码", "登录", "发货", "退货", "物流",
                           "订单号", "快递", "金额", "余额", "绑定", "认证", "投诉", "申请"]
    if not any(w in text for w in specific_indicators):
        score -= 0.2
    return max(score, 0.0)


async def clarify_node(state: AgentState) -> dict:
    """Evaluate input fuzziness and generate clarification if needed."""
    config = get_app_config()
    session_mgr = get_session_manager()
    session_id = state.get("session_id", "")
    user_input = state.get("user_input", "")
    clarify_count = state.get("clarify_count", 0)
    trace_id = get_trace_id()

    logger.info("clarify.eval", input_length=len(user_input), clarify_count=clarify_count, trace_id=trace_id)

    # Quick heuristic check first
    fuzz_score = _quick_fuzz_check(user_input)
    threshold = config.agent.clarify_confidence_threshold

    # If above threshold, no clarification needed
    if fuzz_score >= threshold:
        logger.info("clarify.skip", fuzz_score=fuzz_score, threshold=threshold)
        return {"clarify_count": 0}

    # Max rounds exceeded - give up
    max_rounds = config.agent.max_clarify_rounds
    if clarify_count >= max_rounds:
        logger.info("clarify.give_up", clarify_count=clarify_count, max_rounds=max_rounds)
        return {"clarify_count": clarify_count + 1}

    # Use LLM to generate clarification
    try:
        provider = get_llm_provider("clarify")
        chat_history = await session_mgr.get_history(session_id)
        history_str = "\n".join(f"{h['role']}: {h['content']}" for h in chat_history[-6:])

        prompt = prompt_manager.render("clarify_prompt", {
            "clarify_count": str(clarify_count),
            "max_rounds": str(max_rounds),
        })

        messages = [
            Message(role="system", content=prompt),
            Message(
                role="user",
                content=(
                    f"<conversation_history>\n{history_str}\n</conversation_history>\n\n"
                    f"<user_question>\n{user_input}\n</user_question>"
                ),
            ),
        ]
        response = await provider.chat(messages, temperature=0.5, max_tokens=512)

        # Parse JSON from response
        result = _parse_clarify_response(response.content)

        if not result.need_clarify:
            logger.info("clarify.llm_skip", confidence=result.confidence)
            return {"clarify_count": 0}

        logger.info("clarify.need_clarify", clarify_type=result.clarify_type, confidence=result.confidence)
        return {
            "clarify_count": clarify_count + 1,
            "final_response": {
                "text": result.clarify_message,
                "multimedia": [],
                "quick_replies": [{"label": o, "value": o, "action": ""} for o in (result.options or [])],
                "action": "clarify",
                "metadata": {
                    "trace_id": trace_id,
                    "clarify_type": result.clarify_type,
                    "confidence": result.confidence,
                },
            },
        }

    except Exception as e:
        logger.error("clarify.error", error=str(e))
        # On error, skip clarification
        return {"clarify_count": 0}


def _parse_clarify_response(content: str) -> ClarifyResult:
    """Parse LLM clarification response, falling back to heuristics."""
    try:
        # Try to extract JSON
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group())
            return ClarifyResult(**data)
    except (json.JSONDecodeError, Exception):
        pass

    # Fallback: generate a simple scope clarification
    return ClarifyResult(
        need_clarify=True,
        clarify_type="supplement",
        clarify_message="抱歉，我没太理解您的问题。能否再详细描述一下您遇到的问题？",
        confidence=0.3,
    )
