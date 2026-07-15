from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.agent.types import LLMResponse, Message, ToolDef


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, model: str, api_key: str, timeout: int = 15, max_retries: int = 3):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse: ...

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse: ...

    async def chat_with_timing(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()
        response = await self.chat(messages, temperature, max_tokens, **kwargs)
        response.latency_ms = (time.perf_counter() - start) * 1000
        return response
