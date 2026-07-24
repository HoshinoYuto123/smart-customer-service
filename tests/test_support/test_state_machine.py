from __future__ import annotations

import pytest

from app.support.models import QueueStatus, SelfServiceStatus, ServiceError, TicketStatus
from app.support.policy import is_high_risk, requests_human, sanitize_user_text, transfer_reason
from app.support.state_machine import (
    ensure_queue_transition,
    ensure_self_service_transition,
    ensure_ticket_transition,
)


def test_valid_state_transitions_follow_prd():
    ensure_self_service_transition(SelfServiceStatus.PROCESSING, SelfServiceStatus.SUCCEEDED)
    ensure_queue_transition(QueueStatus.WAITING, QueueStatus.CANCELLED)
    ensure_ticket_transition(TicketStatus.RESOLVED_PENDING, TicketStatus.CLOSED)


def test_invalid_ticket_transition_is_rejected():
    with pytest.raises(ServiceError) as error:
        ensure_ticket_transition(TicketStatus.SUBMITTED, TicketStatus.CLOSED)
    assert error.value.code == "INVALID_STATE"


def test_human_and_high_risk_policy_is_deterministic():
    assert requests_human("请直接转人工")
    assert is_high_risk("账号被盗了")
    assert transfer_reason("发生重复扣款") == "high_risk"
    assert transfer_reason("还是没有解决", unresolved_count=2) == "repeated_unresolved"


def test_sensitive_secrets_are_removed_before_persistence():
    sanitized, changed = sanitize_user_text("密码: hello123 验证码 123456 卡号 6222021234567890")
    assert changed
    assert "hello123" not in sanitized
    assert "123456" not in sanitized
    assert "6222021234567890" not in sanitized
