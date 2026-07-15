from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.agent.nodes.clarify import clarify_node, _quick_fuzz_check


class TestQuickFuzzCheck:
    def test_vague_short_input(self):
        score = _quick_fuzz_check("不好用了")
        assert score < 0.6

    def test_specific_long_input(self):
        score = _quick_fuzz_check("我的订单号12345查不到物流信息，已经发货三天了")
        assert score >= 0.4

    def test_empty_input(self):
        score = _quick_fuzz_check("")
        assert score < 0.5

    def test_with_domain_keyword(self):
        score = _quick_fuzz_check("如何修改我的登录密码")
        assert score >= 0.4


class TestClarifyNode:
    @pytest.mark.asyncio
    async def test_skip_clarify_high_confidence(self, sample_agent_state):
        sample_agent_state["user_input"] = "我的订单号ORD123456查不到物流信息"
        with patch("app.agent.nodes.clarify.get_session_manager") as mock_sm:
            mock_sm.return_value.reset_clarify_count = AsyncMock()
            result = await clarify_node(sample_agent_state)
            assert result.get("clarify_count") == 0

    @pytest.mark.asyncio
    async def test_give_up_after_max_rounds(self, sample_agent_state):
        sample_agent_state["clarify_count"] = 2
        sample_agent_state["user_input"] = "那个"
        result = await clarify_node(sample_agent_state)
        assert result.get("clarify_count") == 3

    @pytest.mark.asyncio
    async def test_generate_clarification(self, sample_agent_state):
        sample_agent_state["user_input"] = "那个功能不好用了"
        sample_agent_state["clarify_count"] = 0

        with patch("app.agent.nodes.clarify.get_session_manager") as mock_sm:
            mock_sm.return_value.get_history = AsyncMock(return_value=[])
            mock_sm.return_value.increment_clarify_count = AsyncMock(return_value=1)

            with patch("app.agent.nodes.clarify.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.chat.return_value.content = '{"need_clarify": true, "clarify_type": "scope", "clarify_message": "您说的是哪个功能？", "options": ["支付功能", "订单功能"], "confidence": 0.4}'
                mock_provider.chat.return_value.latency_ms = 100
                mock_llm.return_value = mock_provider

                with patch("app.agent.nodes.clarify.prompt_manager.render", return_value="test prompt"):
                    result = await clarify_node(sample_agent_state)
                    assert result.get("clarify_count") == 1
                    assert result.get("final_response") is not None
                    assert result["final_response"]["action"] == "clarify"
