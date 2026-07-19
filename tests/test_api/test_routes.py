from __future__ import annotations

import pytest
import uuid
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
        await client.post("/api/v1/auth/anonymous")
        response = await client.post("/api/v1/chat", json={
            "session_id": f"test_{uuid.uuid4().hex}",
            "message": "",
            "context": {"user_id": "u_001", "channel": "web"},
        })
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_mock_flow(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/anonymous")
        with patch("app.agent.service.agent_graph.ainvoke") as mock_invoke:
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
                "session_id": f"test_{uuid.uuid4().hex}",
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
        await client.post("/api/v1/auth/anonymous")
        response = await client.post("/api/v1/chat", json={
            "message": "hello",
        })
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_chat_requires_identity(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat", json={
            "session_id": f"test_{uuid.uuid4().hex}",
            "message": "hello",
        })
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_sessions_are_isolated_by_identity(test_app):
    transport = ASGITransport(app=test_app)
    session_id = f"test_{uuid.uuid4().hex}"
    async with AsyncClient(transport=transport, base_url="http://test") as owner:
        await owner.post("/api/v1/auth/anonymous")
        with patch("app.agent.service.agent_graph.ainvoke") as mock_invoke:
            mock_invoke.return_value = {
                "clarify_count": 0,
                "router_result": {"domain": "order"},
                "final_response": {"text": "ok", "action": "reply"},
            }
            assert (await owner.post("/api/v1/chat", json={"session_id": session_id, "message": "订单"})).status_code == 200

    async with AsyncClient(transport=transport, base_url="http://test") as stranger:
        await stranger.post("/api/v1/auth/anonymous")
        assert (await stranger.get(f"/api/v1/sessions/{session_id}")).status_code == 404
        assert (await stranger.delete(f"/api/v1/sessions/{session_id}")).status_code == 404


@pytest.mark.asyncio
async def test_clarify_count_persists_across_requests(test_app):
    transport = ASGITransport(app=test_app)
    session_id = f"test_{uuid.uuid4().hex}"
    seen_counts = []

    async def invoke(state):
        seen_counts.append(state["clarify_count"])
        next_count = state["clarify_count"] + 1
        return {
            "clarify_count": next_count,
            "final_response": {
                "text": "请补充问题信息",
                "action": "clarify",
                "metadata": {"clarify_count": next_count},
            },
        }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/anonymous")
        with patch("app.agent.service.agent_graph.ainvoke", side_effect=invoke):
            first = await client.post("/api/v1/chat", json={"session_id": session_id, "message": "那个"})
            second = await client.post("/api/v1/chat", json={"session_id": session_id, "message": "还是那个"})
        assert first.status_code == 200
        assert second.status_code == 200
        assert seen_counts == [0, 1]
