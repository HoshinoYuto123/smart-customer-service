"""Central state transitions for support domain objects.

PRD: CS-ST-020 through CS-ST-041, CS-BR-008, CS-BR-015 through CS-BR-017.
"""

from __future__ import annotations

from app.support.models import QueueStatus, SelfServiceStatus, ServiceError, TicketStatus


SELF_SERVICE_TRANSITIONS: dict[SelfServiceStatus, set[SelfServiceStatus]] = {
    SelfServiceStatus.PENDING_VALIDATION: {
        SelfServiceStatus.AWAITING_CONFIRMATION,
        SelfServiceStatus.PROCESSING,
        SelfServiceStatus.INELIGIBLE,
        SelfServiceStatus.FAILED,
    },
    SelfServiceStatus.AWAITING_CONFIRMATION: {
        SelfServiceStatus.PROCESSING,
        SelfServiceStatus.CANCELLED,
    },
    SelfServiceStatus.PROCESSING: {
        SelfServiceStatus.SUCCEEDED,
        SelfServiceStatus.FAILED,
        SelfServiceStatus.UNKNOWN,
    },
    SelfServiceStatus.FAILED: {SelfServiceStatus.PROCESSING},
    SelfServiceStatus.SUCCEEDED: set(),
    SelfServiceStatus.UNKNOWN: set(),
    SelfServiceStatus.INELIGIBLE: set(),
    SelfServiceStatus.CANCELLED: set(),
}

QUEUE_TRANSITIONS: dict[QueueStatus, set[QueueStatus]] = {
    QueueStatus.WAITING: {QueueStatus.CONNECTED, QueueStatus.CANCELLED, QueueStatus.ASYNC_TICKET, QueueStatus.FAILED},
    QueueStatus.CONNECTED: set(),
    QueueStatus.CANCELLED: set(),
    QueueStatus.ASYNC_TICKET: set(),
    QueueStatus.FAILED: {QueueStatus.ASYNC_TICKET},
}

TICKET_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.SUBMITTED: {TicketStatus.PROCESSING, TicketStatus.CANCELLED},
    TicketStatus.PROCESSING: {
        TicketStatus.WAITING_USER,
        TicketStatus.WAITING_EXTERNAL,
        TicketStatus.RESOLVED_PENDING,
    },
    TicketStatus.WAITING_USER: {TicketStatus.PROCESSING, TicketStatus.CANCELLED},
    TicketStatus.WAITING_EXTERNAL: {TicketStatus.PROCESSING, TicketStatus.RESOLVED_PENDING},
    TicketStatus.RESOLVED_PENDING: {TicketStatus.CLOSED, TicketStatus.REOPENED},
    TicketStatus.CLOSED: {TicketStatus.REOPENED},
    TicketStatus.REOPENED: {TicketStatus.PROCESSING},
    TicketStatus.CANCELLED: set(),
}


def ensure_transition(current, target, transitions: dict) -> None:
    """Reject transitions not explicitly allowed by the PRD state machine."""
    if target not in transitions.get(current, set()):
        raise ServiceError(
            "INVALID_STATE",
            f"不能从 {current.value} 变更为 {target.value}",
            status_code=409,
        )


def ensure_self_service_transition(current: SelfServiceStatus, target: SelfServiceStatus) -> None:
    ensure_transition(current, target, SELF_SERVICE_TRANSITIONS)


def ensure_queue_transition(current: QueueStatus, target: QueueStatus) -> None:
    ensure_transition(current, target, QUEUE_TRANSITIONS)


def ensure_ticket_transition(current: TicketStatus, target: TicketStatus) -> None:
    ensure_transition(current, target, TICKET_TRANSITIONS)
