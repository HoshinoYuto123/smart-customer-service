from __future__ import annotations

import time

from anthropic import AsyncAnthropic

from app.agent.types import LLMResponse, Message, ToolDef
from app.llm.provider import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: int = 15, max_retries: int = 3):
        super().__init__(model, api_key, timeout, max_retries)
        self.client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()

        system_msgs = [m.content for m in messages if m.role == "system"]
        chat_msgs = [m for m in messages if m.role != "system"]

        system_prompt = "\n".join(system_msgs) if system_msgs else None
        formatted = [{"role": m.role, "content": m.content} for m in chat_msgs]

        call_kwargs = {
            "model": self.model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            call_kwargs["system"] = system_prompt

        response = await self.client.messages.create(**call_kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens if response.usage else 0,
            finish_reason=response.stop_reason or "stop",
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

        system_msgs = [m.content for m in messages if m.role == "system"]
        chat_msgs = [m for m in messages if m.role != "system"]

        system_prompt = "\n".join(system_msgs) if system_msgs else None
        formatted = [{"role": m.role, "content": m.content} for m in chat_msgs]

        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": {
                    "type": "object",
                    "properties": t.parameters.get("properties", {}),
                    "required": t.parameters.get("required", []),
                },
            }
            for t in tools
        ]

        call_kwargs = {
            "model": self.model,
            "messages": formatted,
            "tools": tool_schemas,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            call_kwargs["system"] = system_prompt

        response = await self.client.messages.create(**call_kwargs)

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "args": block.input,
                })

        return LLMResponse(
            content=content,
            model=response.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens if response.usage else 0,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
