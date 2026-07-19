"""Global tool registry using a decorator-based registration pattern.

Tools register via @tool_registry.register() and are executed by name.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine

from app.agent.types import ToolDef, ToolResult
from app.core.config import get_app_config, get_tool_config
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.retry import is_retryable_error


class ToolRegistry:
    """Global tool registry.

    Tools register via the @tool_registry.register() decorator.
    Supports lookup by name or domain, and async execution with timing.
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(
        self,
        name: str,
        domain: str,
        description: str,
        params_schema: dict | None = None,
        fallback: Callable[..., Coroutine[Any, Any, ToolResult]] | None = None,
    ):
        """Decorator to register a tool function.

        Args:
            name: Unique tool name.
            domain: Business domain this tool belongs to.
            description: Human-readable description for the LLM.
            params_schema: JSON Schema dict describing the tool's parameters.
            fallback: Optional async callable invoked when the primary tool fails.
        """
        if params_schema is None:
            params_schema = {"type": "object", "properties": {}}

        def decorator(func):
            self._tools[name] = {
                "func": func,
                "definition": ToolDef(
                    name=name,
                    description=description,
                    parameters=params_schema,
                ),
                "domain": domain,
                "fallback": fallback,
            }
            return func

        return decorator

    def get_tool(self, name: str) -> dict | None:
        """Return the tool entry dict for *name*, or None."""
        return self._tools.get(name)

    def get_tools_by_domain(self, domain: str) -> list[dict]:
        """Return all tool entries registered under *domain*."""
        return [t for t in self._tools.values() if t["domain"] == domain]

    def list_definitions(self) -> list[ToolDef]:
        """Return the ToolDef for every registered tool."""
        return [t["definition"] for t in self._tools.values()]

    def list_names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools.keys())

    def list_all(self) -> list[dict]:
        """Return all tool entries (full dict with func, definition, domain)."""
        return list(self._tools.values())

    async def execute(self, name: str, params: dict | None = None) -> ToolResult:
        """Execute a registered tool by name.

        Args:
            name: The tool's registered name.
            params: Keyword arguments forwarded to the tool function.

        Returns:
            A ToolResult capturing success/failure and latency.
        """
        if params is None:
            params = {}

        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error_message=f"Tool '{name}' is not registered.",
            )

        item_config = get_tool_config().tools.get(name)
        if item_config and not item_config.enabled:
            return ToolResult(tool_name=name, success=False, error_message=f"Tool '{name}' is disabled.")

        validation_error = self._validate_params(entry["definition"].parameters, params)
        if validation_error:
            return ToolResult(tool_name=name, success=False, error_message=validation_error)

        func = entry["func"]
        fallback = entry.get("fallback")

        start = time.perf_counter()
        try:
            breaker = self._breakers.setdefault(
                name,
                CircuitBreaker(name=f"tool:{name}", failure_predicate=is_retryable_error),
            )
            timeout = item_config.timeout if item_config else 5

            async def invoke():
                retries = get_app_config().retry.tool_max_retries
                delay = get_app_config().retry.tool_delay
                for attempt in range(retries + 1):
                    try:
                        return await asyncio.wait_for(func(params), timeout=timeout)
                    except Exception as exc:
                        if not is_retryable_error(exc) or attempt >= retries:
                            raise
                        await asyncio.sleep(delay * (2 ** attempt))

            data = await breaker.call(invoke)
            latency = (time.perf_counter() - start) * 1000
            if isinstance(data, ToolResult):
                data.latency_ms = round(latency, 2)
                return data
            return ToolResult(
                tool_name=name,
                success=True,
                data=data if isinstance(data, dict) else {"result": data},
                latency_ms=round(latency, 2),
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            if fallback is not None:
                try:
                    fb_result = await fallback(params)
                    fb_result.latency_ms = round(latency, 2)
                    return fb_result
                except Exception as fb_exc:
                    return ToolResult(
                        tool_name=name,
                        success=False,
                        error_message=str(fb_exc),
                        latency_ms=round(latency, 2),
                    )
            message = item_config.fallback_message if item_config and item_config.fallback_message else str(exc)
            return ToolResult(
                tool_name=name,
                success=False,
                error_message=message,
                latency_ms=round(latency, 2),
            )

    @staticmethod
    def _validate_params(schema: dict, params: dict) -> str:
        required = schema.get("required", [])
        missing = [key for key in required if params.get(key) in (None, "")]
        if missing:
            return f"缺少必填参数: {', '.join(missing)}"
        properties = schema.get("properties", {})
        python_types = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict, "array": list}
        for key, value in params.items():
            expected_name = properties.get(key, {}).get("type")
            expected = python_types.get(expected_name)
            if expected and not isinstance(value, expected):
                return f"参数 {key} 类型错误，应为 {expected_name}"
        return ""


# Singleton instance
tool_registry = ToolRegistry()
