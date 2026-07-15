from __future__ import annotations

import pytest
from app.agent.nodes.fallback import fallback_node


class TestFallbackNode:
    @pytest.mark.asyncio
    async def test_clarify_exhausted_transfers_human(self):
        state = {
            "fallback_level": 0,
            "clarify_count": 2,
            "error_history": [],
            "rag_context": [],
        }
        result = await fallback_node(state)
        assert result["should_transfer_human"] is True
        assert result["final_response"]["action"] == "transfer_human"

    @pytest.mark.asyncio
    async def test_level1_uses_rag_context(self):
        state = {
            "fallback_level": 1,
            "clarify_count": 0,
            "error_history": [],
            "rag_context": [{"question": "Q", "answer": "A"}],
        }
        result = await fallback_node(state)
        assert "A" in result["final_response"]["text"]
        assert result["fallback_level"] == 2

    @pytest.mark.asyncio
    async def test_level2_creates_ticket(self):
        state = {
            "fallback_level": 2,
            "clarify_count": 0,
            "error_history": [],
            "rag_context": [],
        }
        result = await fallback_node(state)
        assert result["should_transfer_human"] is True
        assert result["final_response"]["action"] == "create_ticket"
