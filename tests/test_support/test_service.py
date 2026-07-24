from __future__ import annotations

import pytest

import app.support.store as store_module
from app.support.models import Role, SelfServiceStatus, ServiceError, TicketStatus
from app.support.service import SupportService
from app.support.store import SupportStore


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DB_PATH", tmp_path / "support-test.db")
    store = SupportStore()
    store.init_db()
    return SupportService(store=store)


def test_home_marks_all_external_data_as_mock(service):
    home = service.home("user-a")
    assert home["data_mode"] == "mock"
    assert home["context"]["objects"]
    assert all(item["data_mode"] == "mock" for item in home["context"]["objects"])
    assert home["service"]["human_online"] is False
    assert "尚未配置" in home["service"]["message"]


def test_context_objects_are_deterministic_and_user_scoped(service):
    first = service.context("user-a")
    second = service.context("user-a")
    stranger = service.context("user-b")
    assert first["objects"][0]["id"] == second["objects"][0]["id"]
    assert first["objects"][0]["id"] != stranger["objects"][0]["id"]


def test_self_service_is_idempotent_and_unknown_does_not_claim_success(service):
    object_data = service.context("user-a")["objects"][0]
    first, created = service.start_self_service(
        user_id="user-a", capability="logistics_query", object_type="order",
        object_id=object_data["id"], payload={}, idempotency_key="same-key",
    )
    second, created_again = service.start_self_service(
        user_id="user-a", capability="logistics_query", object_type="order",
        object_id=object_data["id"], payload={}, idempotency_key="same-key",
    )
    assert created is True
    assert created_again is False
    assert first.id == second.id
    assert first.status == SelfServiceStatus.SUCCEEDED
    assert first.result["data_mode"] == "mock"

    unknown, _ = service.start_self_service(
        user_id="user-a", capability="logistics_query", object_type="order",
        object_id=object_data["id"], payload={"simulate": "timeout"},
        idempotency_key="unknown-key",
    )
    assert unknown.status == SelfServiceStatus.UNKNOWN
    assert unknown.error_code == "RESULT_UNKNOWN"


def test_self_service_rejects_another_users_object(service):
    strangers_object = service.context("user-b")["objects"][0]
    with pytest.raises(ServiceError) as error:
        service.start_self_service(
            user_id="user-a", capability="logistics_query", object_type="order",
            object_id=strangers_object["id"], payload={}, idempotency_key="forbidden",
        )
    assert error.value.code == "NOT_FOUND"


def test_ticket_owner_isolation_internal_notes_and_state_machine(service):
    ticket, created = service.create_ticket(
        user_id="user-a", session_id="session-a", category="物流问题",
        title="包裹没有更新", description="请帮我核验演示物流",
        object_data={}, idempotency_key="ticket-key",
    )
    assert created
    assert ticket.status == TicketStatus.SUBMITTED

    with pytest.raises(ServiceError) as missing:
        service.get_ticket(ticket_id=ticket.id, user_id="user-b", role=Role.USER)
    assert missing.value.code == "NOT_FOUND"

    with pytest.raises(ServiceError) as forbidden:
        service.add_comment(
            ticket_id=ticket.id, user_id="user-a", role=Role.USER,
            content="内部内容", visibility="internal",
        )
    assert forbidden.value.code == "FORBIDDEN"

    processing = service.transition_ticket(
        ticket_id=ticket.id, user_id="agent-1", role=Role.AGENT,
        target=TicketStatus.PROCESSING, reason="开始处理",
    )
    assert processing.status == TicketStatus.PROCESSING
    with pytest.raises(ServiceError):
        service.transition_ticket(
            ticket_id=ticket.id, user_id="agent-1", role=Role.AGENT,
            target=TicketStatus.CLOSED, reason="非法跳转",
        )


def test_human_request_uses_async_ticket_without_fake_wait_time(service):
    queue = service.request_human(
        user_id="user-a", session_id="session-a", reason="explicit_request",
        summary="请转人工处理", idempotency_key="human-key",
    )
    assert queue.status.value == "async_ticket"
    assert queue.ticket_id
    assert "人数" not in queue.service_message
    assert "分钟" not in queue.service_message


def test_rating_is_unique_and_unresolved_reopens_ticket(service):
    ticket, _ = service.create_ticket(
        user_id="user-a", session_id="session-a", category="课程问题",
        title="课程打不开", description="演示课程无法打开",
        object_data={}, idempotency_key="rating-ticket",
    )
    service.transition_ticket(
        ticket_id=ticket.id, user_id="agent-1", role=Role.AGENT,
        target=TicketStatus.PROCESSING, reason="处理",
    )
    service.transition_ticket(
        ticket_id=ticket.id, user_id="agent-1", role=Role.AGENT,
        target=TicketStatus.RESOLVED_PENDING, reason="给出结论",
    )
    rating, created = service.rate(
        user_id="user-a", service_type="ticket", service_id=ticket.id,
        resolved=False, score=2, reason="仍然打不开",
    )
    assert created
    assert rating.resolved is False
    assert service.get_ticket(ticket_id=ticket.id, user_id="user-a", role=Role.USER).status == TicketStatus.REOPENED

    _, created_again = service.rate(
        user_id="user-a", service_type="ticket", service_id=ticket.id,
        resolved=False, score=2, reason="重复评价",
    )
    assert created_again is False
