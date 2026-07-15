from __future__ import annotations

import time

from app.agent.types import LLMResponse, Message, ToolDef
from app.llm.provider import LLMProvider


class MockProvider(LLMProvider):
    """Mock provider for testing and fallback. Returns deterministic responses."""

    def __init__(self, model: str = "mock", api_key: str = "", timeout: int = 1, max_retries: int = 0):
        super().__init__(model, api_key, timeout, max_retries)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()
        return LLMResponse(
            content="这是 Mock 回复。请稍等，正在为您转接人工客服。",
            model="mock",
            tokens_used=10,
            finish_reason="stop",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()
        return LLMResponse(
            content="这是模拟工具调用回复。请稍等，正在为您处理。",
            model="mock",
            tokens_used=10,
            tool_calls=[],
            finish_reason="stop",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
