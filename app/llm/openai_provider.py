from __future__ import annotations

import json
import time

from openai import AsyncOpenAI

from app.agent.types import LLMResponse, Message, ToolDef
from app.llm.provider import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: int = 15, max_retries: int = 3):
        super().__init__(model, api_key, timeout, max_retries)
        kwargs = {"api_key": api_key, "timeout": timeout, "max_retries": max_retries}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()
        formatted = [{"role": m.role, "content": m.content} for m in messages]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=formatted,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            finish_reason=choice.finish_reason or "stop",
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
        formatted = [{"role": m.role, "content": m.content} for m in messages]

        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=formatted,
            tools=tool_schemas,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                })

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
