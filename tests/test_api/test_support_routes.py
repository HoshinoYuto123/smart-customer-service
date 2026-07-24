from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.support as support_api
import app.support.store as store_module
from app.main import create_app
from app.support.service import SupportService
from app.support.store import SupportStore


@pytest.fixture
def support_app(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DB_PATH", tmp_path / "support-api.db")
    store = SupportStore()
    store.init_db()
    monkeypatch.setattr(support_api, "support_service", SupportService(store=store))
    return create_app()


async def auth(client: AsyncClient):
    response = await client.post("/api/v1/auth/anonymous")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_support_home_context_and_faq_flow(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        identity = await auth(client)
        assert identity["role"] == "user"

        home = await client.get("/api/v1/support/home")
        assert home.status_code == 200
        data = home.json()["data"]
        assert data["data_mode"] == "mock"
        assert data["categories"]
        assert len(data["capabilities"]) == 13

        faqs = await client.get("/api/v1/support/faqs", params={"q": "物流"})
        assert faqs.status_code == 200
        assert faqs.json()["data"]
        article_id = faqs.json()["data"][0]["id"]
        detail = await client.get(f"/api/v1/support/faqs/{article_id}")
        assert detail.status_code == 200

        feedback = await client.post(
            f"/api/v1/support/faqs/{article_id}/feedback",
            json={"resolved": False, "reason": "没有解决", "session_id": "s1"},
        )
        assert feedback.status_code == 200
        assert feedback.json()["data"]["next_actions"] == ["chat", "human"]


@pytest.mark.asyncio
async def test_self_service_api_is_idempotent_and_owner_scoped(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner:
        await auth(owner)
        context = (await owner.get("/api/v1/support/context")).json()["data"]
        order = next(item for item in context["objects"] if item["type"] == "order")
        payload = {"capability": "logistics_query", "object_type": "order", "object_id": order["id"], "input": {}}
        first = await owner.post("/api/v1/support/self-service", json=payload, headers={"Idempotency-Key": "api-key"})
        second = await owner.post("/api/v1/support/self-service", json=payload, headers={"Idempotency-Key": "api-key"})
        assert first.status_code == 200
        assert second.json()["meta"]["deduplicated"] is True
        task_id = first.json()["data"]["id"]

    async with AsyncClient(transport=transport, base_url="http://test") as stranger:
        await auth(stranger)
        hidden = await stranger.get(f"/api/v1/support/self-service/{task_id}")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_ticket_flow_permissions_and_agent_workspace(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as user:
        await auth(user)
        created = await user.post(
            "/api/v1/support/tickets",
            headers={"Idempotency-Key": "ticket-api-key"},
            json={
                "session_id": "session-1", "category": "物流问题",
                "title": "物流没有更新", "description": "请核验演示订单", "object": {},
            },
        )
        assert created.status_code == 200
        ticket_id = created.json()["data"]["id"]
        internal = await user.post(
            f"/api/v1/support/tickets/{ticket_id}/comments",
            json={"content": "用户不应写内部备注", "visibility": "internal"},
        )
        assert internal.status_code == 403
        workspace = await user.get("/api/v1/agent/workspace")
        assert workspace.status_code == 403

    async with AsyncClient(transport=transport, base_url="http://test") as agent:
        role = await agent.post("/api/v1/auth/demo-role", json={"role": "agent"})
        assert role.status_code == 200
        workspace = await agent.get("/api/v1/agent/workspace")
        assert workspace.status_code == 200
        assert any(item["id"] == ticket_id for item in workspace.json()["data"]["tickets"])
        processing = await agent.post(
            f"/api/v1/support/tickets/{ticket_id}/transitions",
            json={"target": "processing", "reason": "开始处理"},
        )
        assert processing.status_code == 200
        assert processing.json()["data"]["status"] == "processing"


@pytest.mark.asyncio
async def test_transfer_progress_and_rating_do_not_invent_wait_time(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await auth(client)
        transfer = await client.post(
            "/api/v1/support/queue",
            headers={"Idempotency-Key": "human-api-key"},
            json={"session_id": "session-2", "reason": "explicit_request", "summary": "我要人工"},
        )
        assert transfer.status_code == 200
        entry = transfer.json()["data"]
        assert entry["status"] == "async_ticket"
        assert "人数" not in entry["service_message"]
        assert "分钟" not in entry["service_message"]

        progress = await client.get("/api/v1/support/progress")
        assert progress.status_code == 200
        assert progress.json()["data"]["tickets"]

        ticket_id = entry["ticket_id"]
        rating = await client.post(
            "/api/v1/support/ratings",
            json={"service_type": "ticket", "service_id": ticket_id, "resolved": True, "score": 5, "reason": "演示评价"},
        )
        assert rating.status_code == 200
        duplicate = await client.post(
            "/api/v1/support/ratings",
            json={"service_type": "ticket", "service_id": ticket_id, "resolved": True, "score": 5, "reason": "重复"},
        )
        assert duplicate.json()["meta"]["deduplicated"] is True


@pytest.mark.asyncio
async def test_api_rejects_missing_idempotency_key(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await auth(client)
        response = await client.post(
            "/api/v1/support/tickets",
            json={"category": "其他", "title": "问题", "description": "说明", "object": {}},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_anonymous_endpoint_drops_demo_agent_role(support_app):
    transport = ASGITransport(app=support_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        role_response = await client.post("/api/v1/auth/demo-role", json={"role": "agent"})
        assert role_response.status_code == 200
        assert role_response.json()["role"] == "agent"

        user_response = await client.post("/api/v1/auth/anonymous")
        assert user_response.status_code == 200
        assert user_response.json()["role"] == "user"
        assert user_response.json()["user_id"] != role_response.json()["user_id"]
