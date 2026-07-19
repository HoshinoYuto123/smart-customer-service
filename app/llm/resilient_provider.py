"""Cross-provider concurrency, timeout, retry and circuit-breaker boundary."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable

from app.agent.types import LLMResponse, Message, ToolDef
from app.core.config import get_app_config
from app.llm.provider import LLMProvider
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.retry import is_retryable_error

_config = get_app_config()
_semaphore = asyncio.Semaphore(_config.concurrency.max_concurrent_llm_calls)
_queue_lock = threading.Lock()
_waiting = 0


class LLMQueueFullError(RuntimeError):
    pass


class ResilientLLMProvider(LLMProvider):
    def __init__(self, delegate: LLMProvider) -> None:
        super().__init__(delegate.model, delegate.api_key, delegate.timeout, delegate.max_retries)
        self.delegate = delegate
        self.breaker = CircuitBreaker(
            name=f"llm:{delegate.model}",
            failure_predicate=is_retryable_error,
        )

    async def _run(self, operation: Callable[[], Awaitable[LLMResponse]]) -> LLMResponse:
        global _waiting
        config = get_app_config()
        with _queue_lock:
            if _waiting >= config.concurrency.request_queue_max_size:
                raise LLMQueueFullError("LLM request queue is full")
            _waiting += 1

        acquired = False
        try:
            await asyncio.wait_for(_semaphore.acquire(), timeout=config.agent.llm_timeout)
            acquired = True

            async def invoke() -> LLMResponse:
                last_error: Exception | None = None
                for attempt in range(config.retry.llm_max_retries + 1):
                    try:
                        return await asyncio.wait_for(operation(), timeout=config.agent.llm_timeout)
                    except Exception as exc:
                        last_error = exc
                        if not is_retryable_error(exc) or attempt >= config.retry.llm_max_retries:
                            raise
                        await asyncio.sleep(config.retry.llm_base_delay * (2 ** attempt))
                raise last_error or RuntimeError("LLM retry exhausted")

            return await self.breaker.call(invoke)
        finally:
            with _queue_lock:
                _waiting = max(0, _waiting - 1)
            if acquired:
                _semaphore.release()

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        return await self._run(
            lambda: self.delegate.chat(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        )

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDef],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        return await self._run(
            lambda: self.delegate.chat_with_tools(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        )
