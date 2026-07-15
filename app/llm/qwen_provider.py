from __future__ import annotations

import time

import dashscope
from dashscope import AioGeneration

from app.agent.types import LLMResponse, Message, ToolDef
from app.llm.provider import LLMProvider


class QwenProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: int = 15, max_retries: int = 3):
        super().__init__(model, api_key, timeout, max_retries)
        dashscope.api_key = api_key

    def _format_messages(self, messages: list[Message]) -> list[dict]:
        formatted = []
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.role == "system":
                # DashScope uses "system" role
                pass
            formatted.append(msg)
        return formatted

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        start = time.perf_counter()

        formatted = self._format_messages(messages)

        response = await AioGeneration.call(
            model=self.model,
            messages=formatted,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format="message",
            **kwargs,
        )

        if response.status_code != 200:
            return LLMResponse(
                content=f"Error: {response.message}",
                model=self.model,
                finish_reason="error",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        output = response.output
        content = ""
        if output and output.choices:
            content = output.choices[0].message.get("content", "")

        tokens = output.usage.total_tokens if output and output.usage else 0

        return LLMResponse(
            content=content,
            model=self.model,
            tokens_used=tokens,
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
        # Qwen DashScope tools not fully supported in async mode;
        # fall back to prompting the tool list
        tool_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools)
        system_msg = Message(
            role="system",
            content=f"You have access to these tools. Respond with a JSON indicating which tool to call:\n{tool_desc}",
        )
        return await self.chat([system_msg] + messages, temperature, max_tokens, **kwargs)
