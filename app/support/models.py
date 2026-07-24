"""Typed domain models for the support service.

PRD: CS-FN-002, CS-FN-005, CS-FN-007, CS-FN-009, CS-FN-011.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    GUEST = "guest"
    USER = "user"
    MEMBER = "member"
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    ADMIN = "admin"


STAFF_ROLES = {Role.AGENT, Role.SUPERVISOR, Role.OPERATOR, Role.ADMIN}
AGENT_ROLES = {Role.AGENT, Role.SUPERVISOR, Role.ADMIN}


class SelfServiceStatus(str, Enum):
    PENDING_VALIDATION = "pending_validation"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    INELIGIBLE = "ineligible"
    CANCELLED = "cancelled"


class QueueStatus(str, Enum):
    WAITING = "waiting"
    CONNECTED = "connected"
    CANCELLED = "cancelled"
    ASYNC_TICKET = "async_ticket"
    FAILED = "failed"


class TicketStatus(str, Enum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    WAITING_USER = "waiting_user"
    WAITING_EXTERNAL = "waiting_external"
    RESOLVED_PENDING = "resolved_pending"
    CLOSED = "closed"
    REOPENED = "reopened"
    CANCELLED = "cancelled"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    RETRYABLE_FAILED = "retryable_failed"
    FINAL_FAILED = "final_failed"
    READ = "read"


class SupportObject(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str = ""
    status: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)
    data_mode: str = "mock"


class SupportContext(BaseModel):
    user: dict[str, Any]
    objects: list[SupportObject] = Field(default_factory=list)
    selected_object_id: str = ""
    data_mode: str = "mock"


class Capability(BaseModel):
    id: str
    title: str
    description: str
    object_types: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    enabled: bool = True
    risk: str = "standard"
    data_mode: str = "mock"


class SelfServiceTask(BaseModel):
    id: str
    user_id: str
    capability: str
    object_type: str = ""
    object_id: str = ""
    status: SelfServiceStatus
    input: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""
    idempotency_key: str
    data_mode: str = "mock"
    created_at: str
    updated_at: str


class QueueEntry(BaseModel):
    id: str
    session_id: str
    user_id: str
    reason: str
    priority: str = "standard"
    status: QueueStatus
    summary: str = ""
    ticket_id: str = ""
    service_message: str = ""
    data_mode: str = "mock"
    created_at: str
    updated_at: str


class TicketComment(BaseModel):
    id: str
    ticket_id: str
    author_id: str
    author_role: Role
    content: str
    visibility: str = "public"
    created_at: str


class TicketHistory(BaseModel):
    id: str
    ticket_id: str
    from_status: str = ""
    to_status: TicketStatus
    actor_id: str
    reason: str = ""
    created_at: str


class SupportTicket(BaseModel):
    id: str
    user_id: str
    session_id: str = ""
    category: str
    title: str
    description: str
    status: TicketStatus
    priority: str = "standard"
    object: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    data_mode: str = "mock"
    created_at: str
    updated_at: str
    comments: list[TicketComment] = Field(default_factory=list)
    history: list[TicketHistory] = Field(default_factory=list)


class Rating(BaseModel):
    id: str
    user_id: str
    service_type: str
    service_id: str
    resolved: bool
    score: int | None = Field(default=None, ge=1, le=5)
    reason: str = ""
    created_at: str


class FAQArticle(BaseModel):
    id: str
    category_id: str
    domain: str
    question: str
    answer: str
    keywords: list[str] = Field(default_factory=list)
    related_faqs: list[str] = Field(default_factory=list)
    version: int = 1
    status: str = "active"
    scope: str = "通用说明；具体业务状态以页面和人工核验为准"
    data_mode: str = "legacy_demo"


class ServiceError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
