from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_health_check(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "providers" in data


@pytest.mark.asyncio
async def test_chat_empty_message(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat", json={
            "session_id": "test_001",
            "message": "",
            "context": {"user_id": "u_001", "channel": "web"},
        })
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_mock_flow(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.api.routes.agent_graph.ainvoke") as mock_invoke:
            mock_invoke.return_value = {
                "final_response": {
                    "text": "测试回复",
                    "multimedia": [],
                    "quick_replies": [],
                    "action": "reply",
                    "metadata": {"trace_id": "test_001"},
                }
            }

            response = await client.post("/api/v1/chat", json={
                "session_id": "test_001",
                "message": "我的订单还没发货",
                "context": {"user_id": "u_001", "channel": "web"},
            })

            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert data["response"]["text"] == "测试回复"


@pytest.mark.asyncio
async def test_chat_missing_session_id(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat", json={
            "message": "hello",
        })
        assert response.status_code == 422  # Validation error
