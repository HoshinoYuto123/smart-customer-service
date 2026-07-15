from __future__ import annotations

import pytest
from app.tools.registry import tool_registry, ToolRegistry


class TestToolRegistry:
    def setup_method(self):
        # Use a fresh registry for testing
        self.registry = ToolRegistry()

    def test_register_tool(self):
        @self.registry.register(
            name="test_tool",
            domain="test",
            description="A test tool",
            params_schema={"type": "object", "properties": {}, "required": []},
        )
        async def test_tool(params):
            from app.agent.types import ToolResult
            return ToolResult(tool_name="test_tool", success=True, data={"message": "test"})

        assert "test_tool" in self.registry.list_names()

    def test_get_tool(self):
        @self.registry.register(
            name="my_tool",
            domain="test",
            description="My tool",
            params_schema={"type": "object", "properties": {}, "required": []},
        )
        async def my_tool(params):
            from app.agent.types import ToolResult
            return ToolResult(tool_name="my_tool", success=True)

        tool = self.registry.get_tool("my_tool")
        assert tool is not None
        assert tool["definition"].name == "my_tool"

    def test_get_nonexistent_tool(self):
        assert self.registry.get_tool("nonexistent") is None

    def test_get_tools_by_domain(self):
        @self.registry.register(name="t1", domain="a", description="T1", params_schema={})
        async def t1(params):
            from app.agent.types import ToolResult
            return ToolResult(tool_name="t1", success=True)

        @self.registry.register(name="t2", domain="b", description="T2", params_schema={})
        async def t2(params):
            from app.agent.types import ToolResult
            return ToolResult(tool_name="t2", success=True)

        a_tools = self.registry.get_tools_by_domain("a")
        assert len(a_tools) == 1
        assert a_tools[0]["definition"].name == "t1"

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        @self.registry.register(
            name="calc",
            domain="math",
            description="Calculate",
            params_schema={"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]},
        )
        async def calc(params):
            from app.agent.types import ToolResult
            return ToolResult(tool_name="calc", success=True, data={"result": params["x"] * 2})

        result = await self.registry.execute("calc", {"x": 5})
        assert result.success
        assert result.data["result"] == 10

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        result = await self.registry.execute("no_such_tool", {})
        assert not result.success
        assert "not registered" in result.error_message.lower()
