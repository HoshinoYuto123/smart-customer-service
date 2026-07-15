from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.state import AgentState
from app.agent.types import (
    Message, LLMResponse, ClarifyResult, RouteDecision, AgentResponse,
    ToolResult, FAQItem, QuickReply, MultimediaItem,
)


@pytest.fixture
def mock_llm_response():
    return LLMResponse(
        content="这是一个测试回复。",
        model="mock",
        tokens_used=50,
        finish_reason="stop",
        latency_ms=100.0,
    )


@pytest.fixture
def mock_clarify_result():
    return ClarifyResult(
        need_clarify=True,
        clarify_type="scope",
        clarify_message="请问您说的是账户问题还是订单问题？",
        options=["账户问题", "订单问题"],
        confidence=0.4,
    )


@pytest.fixture
def mock_route_decision():
    return RouteDecision(
        domain="order",
        sub_intent="query_order_status",
        confidence=0.85,
        suggested_tools=["faq_search", "query_order"],
        reasoning="用户询问订单状态，匹配order域",
    )


@pytest.fixture
def sample_agent_state() -> AgentState:
    return AgentState(
        messages=[],
        session_id="test_session_001",
        user_input="我的订单怎么还没发货",
        user_id="u_001",
        channel="web",
        clarify_count=0,
        clarify_history=[],
        router_result=None,
        router_trace=[],
        rag_context=[],
        tool_calls=[],
        tool_results=[],
        final_response=None,
        should_transfer_human=False,
        fallback_level=0,
        error_history=[],
        trace_id="test_trace_001",
    )


@pytest.fixture
def sample_faq_items() -> list[dict]:
    return [
        {
            "id": "order_faq_001",
            "domain": "order",
            "question": "如何查询订单物流状态？",
            "answer": "您可以在「我的订单」中点击对应订单查看物流详情。",
            "keywords": ["物流", "订单", "查询", "快递"],
            "related_faqs": ["order_faq_002"],
            "version": 1,
            "status": "active",
        },
        {
            "id": "account_faq_001",
            "domain": "account",
            "question": "如何修改登录密码？",
            "answer": "在「账户设置」-「安全中心」中可修改密码。",
            "keywords": ["密码", "修改", "账户", "安全"],
            "related_faqs": [],
            "version": 1,
            "status": "active",
        },
    ]


@pytest.fixture
def mock_agent_response() -> AgentResponse:
    return AgentResponse(
        text="您的订单正在配送中，预计明天到达。",
        multimedia=[],
        quick_replies=[
            QuickReply(label="查看物流", value="查看物流详情"),
            QuickReply(label="联系人工", value="转人工", action="transfer_human"),
        ],
        action="reply",
        metadata={"trace_id": "test_001", "router_domain": "order"},
    )
