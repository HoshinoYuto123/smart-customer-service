"""Customer support REST API.

PRD: CS-FN-001 through CS-FN-012. All external business data returned by
this module is explicitly marked as Mock until real adapters are configured.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from app.core.auth import Principal, get_request_principal
from app.core.di import get_session_manager
from app.core.observability import get_trace_id
from app.support.models import AGENT_ROLES, Role, ServiceError, TicketStatus
from app.support.service import support_service


router = APIRouter(prefix="/api/v1/support", tags=["support"])
agent_router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def envelope(data: Any, **meta) -> dict:
    result = {"success": True, "data": data, "error": None, "trace_id": get_trace_id()}
    if meta:
        result["meta"] = meta
    return result


def require_agent(principal: Principal = Depends(get_request_principal)) -> Principal:
    if principal.role not in AGENT_ROLES:
        raise ServiceError("FORBIDDEN", "无权访问人工客服工作台", status_code=403)
    return principal


class SessionCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    context: dict[str, Any] = Field(default_factory=dict)


class FAQFeedbackRequest(BaseModel):
    resolved: bool
    reason: str = Field(default="", max_length=500)
    session_id: str = Field(default="", max_length=128)


class SelfServiceRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=64)
    object_type: str = Field(default="", max_length=32)
    object_id: str = Field(default="", max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)


class QueueRequest(BaseModel):
    session_id: str = Field(default="", max_length=128)
    reason: str = Field(default="explicit_request", max_length=64)
    summary: str = Field(default="", max_length=2000)


class TicketCreateRequest(BaseModel):
    session_id: str = Field(default="", max_length=128)
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    object: dict[str, Any] = Field(default_factory=dict)


class CommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=3000)
    visibility: str = Field(default="public", pattern=r"^(public|internal)$")


class TicketTransitionRequest(BaseModel):
    target: TicketStatus
    reason: str = Field(default="", max_length=500)


class RatingRequest(BaseModel):
    service_type: str = Field(pattern=r"^(session|ticket|self_service)$")
    service_id: str = Field(min_length=1, max_length=128)
    resolved: bool
    score: int | None = Field(default=None, ge=1, le=5)
    reason: str = Field(default="", max_length=500)


class EventRequest(BaseModel):
    event_name: str = Field(min_length=1, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


@router.get("/home")
def support_home(principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.home(principal.user_id))


@router.get("/context")
def support_context(principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.context(principal.user_id))


@router.get("/categories")
def categories(principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.categories())


@router.get("/faqs")
def faqs(
    q: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=64),
    principal: Principal = Depends(get_request_principal),
):
    items = support_service.search_faqs(q, category)
    return envelope([item.model_dump() for item in items], total=len(items))


@router.get("/faqs/{article_id}")
def faq_detail(article_id: str, principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.faq_detail(article_id).model_dump())


@router.post("/faqs/{article_id}/feedback")
def faq_feedback(
    article_id: str,
    request: FAQFeedbackRequest,
    principal: Principal = Depends(get_request_principal),
):
    return envelope(support_service.faq_feedback(
        article_id=article_id, user_id=principal.user_id, session_id=request.session_id,
        resolved=request.resolved, reason=request.reason,
    ))


@router.post("/sessions")
async def create_support_session(
    request: SessionCreateRequest,
    principal: Principal = Depends(get_request_principal),
):
    session = await get_session_manager().get_or_create(
        request.session_id, user_id=principal.user_id, channel="web"
    )
    return envelope({
        "id": session.session_id,
        "user_id": session.user_id,
        "channel": session.channel,
        "context": request.context,
    })


@router.post("/self-service")
def start_self_service(
    request: SelfServiceRequest,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    principal: Principal = Depends(get_request_principal),
):
    task, created = support_service.start_self_service(
        user_id=principal.user_id, capability=request.capability,
        object_type=request.object_type, object_id=request.object_id,
        payload=request.input, idempotency_key=idempotency_key,
    )
    return envelope(task.model_dump(), created=created, deduplicated=not created)


@router.get("/self-service/{task_id}")
def self_service_status(task_id: str, principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.get_task(
        task_id=task_id, user_id=principal.user_id, role=principal.role
    ).model_dump())


@router.post("/queue")
def request_human(
    request: QueueRequest,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    principal: Principal = Depends(get_request_principal),
):
    if not idempotency_key:
        raise ServiceError("VALIDATION_ERROR", "缺少有效的幂等标识")
    entry = support_service.request_human(
        user_id=principal.user_id, session_id=request.session_id,
        reason=request.reason, summary=request.summary,
        idempotency_key=idempotency_key,
    )
    return envelope(entry.model_dump())


@router.get("/queue/{queue_id}")
def queue_status(queue_id: str, principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.get_queue(
        queue_id=queue_id, user_id=principal.user_id, role=principal.role
    ).model_dump())


@router.delete("/queue/{queue_id}")
def cancel_queue(queue_id: str, principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.cancel_queue(queue_id=queue_id, user_id=principal.user_id).model_dump())


@router.post("/tickets")
def create_ticket(
    request: TicketCreateRequest,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    principal: Principal = Depends(get_request_principal),
):
    ticket, created = support_service.create_ticket(
        user_id=principal.user_id, session_id=request.session_id,
        category=request.category, title=request.title, description=request.description,
        object_data=request.object, idempotency_key=idempotency_key,
    )
    return envelope(ticket.model_dump(), created=created, deduplicated=not created)


@router.get("/tickets")
def list_tickets(principal: Principal = Depends(get_request_principal)):
    tickets = support_service.list_tickets(user_id=principal.user_id, role=principal.role)
    return envelope([ticket.model_dump() for ticket in tickets], total=len(tickets))


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.get_ticket(
        ticket_id=ticket_id, user_id=principal.user_id, role=principal.role
    ).model_dump())


@router.post("/tickets/{ticket_id}/comments")
def add_ticket_comment(
    ticket_id: str,
    request: CommentCreateRequest,
    principal: Principal = Depends(get_request_principal),
):
    comment = support_service.add_comment(
        ticket_id=ticket_id, user_id=principal.user_id, role=principal.role,
        content=request.content, visibility=request.visibility,
    )
    return envelope(comment.model_dump())


@router.post("/tickets/{ticket_id}/transitions")
def transition_ticket(
    ticket_id: str,
    request: TicketTransitionRequest,
    principal: Principal = Depends(get_request_principal),
):
    ticket = support_service.transition_ticket(
        ticket_id=ticket_id, user_id=principal.user_id, role=principal.role,
        target=request.target, reason=request.reason,
    )
    return envelope(ticket.model_dump())


@router.get("/progress")
def progress(principal: Principal = Depends(get_request_principal)):
    return envelope(support_service.progress(principal.user_id))


@router.post("/ratings")
def create_rating(request: RatingRequest, principal: Principal = Depends(get_request_principal)):
    rating, created = support_service.rate(
        user_id=principal.user_id, service_type=request.service_type,
        service_id=request.service_id, resolved=request.resolved,
        score=request.score, reason=request.reason,
    )
    return envelope(rating.model_dump(), created=created, deduplicated=not created)


@router.post("/events")
def record_event(request: EventRequest, principal: Principal = Depends(get_request_principal)):
    event_id = support_service.record_event(
        user_id=principal.user_id, event_name=request.event_name,
        properties=request.properties,
    )
    return envelope({"event_id": event_id, "accepted": True})


@agent_router.get("/workspace")
def agent_workspace(principal: Principal = Depends(require_agent)):
    return envelope(support_service.workspace(principal.role))
