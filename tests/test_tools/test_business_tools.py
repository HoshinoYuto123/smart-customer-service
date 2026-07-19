from __future__ import annotations

import pytest

from app.tools.query_order import query_order
from app.tools.query_account import query_account
from app.tools.registry import ToolRegistry
from app.core.config import get_app_config


@pytest.mark.asyncio
async def test_unknown_order_is_not_fabricated():
    result = await query_order({"order_id": "ORD999999999", "query": "ORD999999999"})
    assert result.success
    assert result.data["orders"] == []
    assert result.data["is_demo_data"] is True


@pytest.mark.asyncio
async def test_demo_account_is_stable_and_marked():
    first = await query_account({"user_id": "U123456"})
    second = await query_account({"user_id": "U123456"})
    assert first.data["is_demo_data"] is True
    assert first.data["account"]["balance"] == second.data["account"]["balance"]
    assert first.data["account"]["points"] == second.data["account"]["points"]


@pytest.mark.asyncio
async def test_production_business_tools_fail_closed(monkeypatch):
    monkeypatch.setattr(get_app_config().app, "mode", "production")
    order = await query_order({"order_id": "ORD123456", "query": "ORD123456"})
    account = await query_account({"user_id": "U123456"})
    assert not order.success
    assert not account.success


@pytest.mark.asyncio
async def test_registry_validates_required_parameters():
    registry = ToolRegistry()

    @registry.register(
        name="required_tool",
        domain="test",
        description="test",
        params_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    async def required_tool(params):
        return {"value": params["value"]}

    result = await registry.execute("required_tool", {})
    assert not result.success
    assert "value" in result.error_message
