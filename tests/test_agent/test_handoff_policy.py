from __future__ import annotations

import pytest

import app.agent.service as agent_service
import app.support.store as store_module
from app.agent.types import SessionContext
from app.support.adapters import MockBusinessAdapter
from app.support.service import SupportService
from app.support.store import SupportStore


class RecordingSessionManager:
    def __init__(self) -> None:
        self.turns: list[dict] = []

    async def record_turn(self, session_id: str, **kwargs) -> None:
        self.turns.append({"session_id": session_id, **kwargs})


@pytest.fixture
def handoff_service(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DB_PATH", tmp_path / "support.db")
    store = SupportStore()
    store.init_db()
    service = SupportService(
        store=store,
        adapter=MockBusinessAdapter(),
    )
    monkeypatch.setattr(agent_service, "support_service", service)
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        ("我要转人工客服", "explicit_request"),
        ("我的账号被盗了", "high_risk"),
    ],
)
async def test_deterministic_handoff_preempts_agent_graph(
    handoff_service, message, expected_reason
):
    manager = RecordingSessionManager()
    response = await agent_service.run_agent_turn(
        session_manager=manager,
        session=SessionContext(session_id="s-policy", user_id="u-policy"),
        message=message,
        user_id="u-policy",
        channel="web",
        trace_id="trace-policy",
    )

    assert response.action == "transfer_human"
    assert response.metadata["reason"] == expected_reason
    assert response.metadata["data_mode"] == "mock"
    assert response.metadata["ticket_id"]
    assert manager.turns[0]["unresolved_count"] == 0


@pytest.mark.asyncio
async def test_second_consecutive_unresolved_report_triggers_handoff(handoff_service):
    manager = RecordingSessionManager()
    response = await agent_service.run_agent_turn(
        session_manager=manager,
        session=SessionContext(
            session_id="s-repeat", user_id="u-repeat", unresolved_count=1
        ),
        message="还是没有解决",
        user_id="u-repeat",
        channel="web",
        trace_id="trace-repeat",
    )

    assert response.action == "transfer_human"
    assert response.metadata["reason"] == "repeated_unresolved"
    assert manager.turns[0]["unresolved_count"] == 2


@pytest.mark.asyncio
async def test_handoff_summary_redacts_password(handoff_service):
    manager = RecordingSessionManager()
    response = await agent_service.run_agent_turn(
        session_manager=manager,
        session=SessionContext(session_id="s-secret", user_id="u-secret"),
        message="我要人工，password: super-secret",
        user_id="u-secret",
        channel="web",
        trace_id="trace-secret",
    )

    ticket = handoff_service.get_ticket(
        ticket_id=response.metadata["ticket_id"], user_id="u-secret", role="user"
    )
    assert "super-secret" not in ticket.description
    assert response.metadata["sensitive_data_removed"] is True
