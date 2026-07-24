"""Application service for the customer support MVP.

PRD: CS-FN-001 through CS-FN-012. External business actions currently use
the explicit ``MockBusinessAdapter`` and never claim production completion.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.core.config import get_app_config
from app.core.observability import get_trace_id
from app.support.adapters import BusinessAdapter, MockBusinessAdapter
from app.support.catalog import CATEGORIES, get_article, search_articles
from app.support.models import (
    AGENT_ROLES,
    FAQArticle,
    QueueEntry,
    QueueStatus,
    Rating,
    Role,
    SelfServiceTask,
    ServiceError,
    SupportTicket,
    TicketComment,
    TicketStatus,
)
from app.support.policy import sanitize_user_text, summarize_for_handoff
from app.support.state_machine import ensure_queue_transition, ensure_ticket_transition
from app.support.store import SupportStore, support_store


ALLOWED_EVENTS = {
    "support_entry_view", "support_entry_click", "context_loaded", "context_changed",
    "category_click", "faq_search", "faq_no_result", "faq_view", "faq_feedback",
    "self_service_start", "self_service_result", "human_requested", "queue_started",
    "queue_cancelled", "ticket_created", "ticket_status_changed", "resolution_confirmed",
    "rating_submitted", "notification_result",
}


class SupportService:
    def __init__(self, *, store: SupportStore | None = None, adapter: BusinessAdapter | None = None):
        self.store = store or support_store
        self.adapter = adapter or MockBusinessAdapter()

    def home(self, user_id: str) -> dict[str, Any]:
        context = self.adapter.get_context(user_id)
        return {
            "context": context.model_dump(),
            "categories": CATEGORIES,
            "featured_faqs": [item.model_dump() for item in search_articles(limit=6)],
            "capabilities": [item.model_dump() for item in self.adapter.capabilities()],
            "service": {
                "human_online": False,
                "availability_source": "not_configured",
                "offline_action": "create_ticket",
                "message": "人工服务时间尚未配置；需要人工时可立即提交异步工单。",
            },
            "data_mode": self.adapter.data_mode,
            "disclaimer": "订单、课程、自助和通知当前均为本地 Mock；未接入真实业务系统。",
        }

    def context(self, user_id: str) -> dict[str, Any]:
        return self.adapter.get_context(user_id).model_dump()

    def categories(self) -> list[dict]:
        return CATEGORIES

    def search_faqs(self, query: str = "", category: str = "") -> list[FAQArticle]:
        return search_articles(query, category)

    def faq_detail(self, article_id: str) -> FAQArticle:
        article = get_article(article_id)
        if not article:
            raise ServiceError("NOT_FOUND", "FAQ 不存在或已下线", status_code=404)
        return article

    def faq_feedback(
        self, *, article_id: str, user_id: str, session_id: str,
        resolved: bool, reason: str,
    ) -> dict:
        self.faq_detail(article_id)
        safe_reason, _ = sanitize_user_text(reason[:500])
        row = self.store.upsert_faq_feedback(
            article_id=article_id, user_id=user_id, session_id=session_id,
            resolved=resolved, reason=safe_reason,
        )
        return {
            "id": row["id"], "resolved": bool(row["resolved"]),
            "next_actions": [] if resolved else ["chat", "human"],
        }

    def _owns_object(self, user_id: str, object_id: str) -> bool:
        if not object_id:
            return True
        return any(item.id == object_id for item in self.adapter.get_context(user_id).objects)

    def start_self_service(
        self, *, user_id: str, capability: str, object_type: str, object_id: str,
        payload: dict, idempotency_key: str,
    ) -> tuple[SelfServiceTask, bool]:
        capability_def = next((item for item in self.adapter.capabilities() if item.id == capability), None)
        if not capability_def or not capability_def.enabled:
            raise ServiceError("NOT_FOUND", "自助服务不存在或已停用", status_code=404)
        if capability_def.object_types and object_type not in capability_def.object_types:
            raise ServiceError("VALIDATION_ERROR", "当前业务对象不适用于该服务")
        if not self._owns_object(user_id, object_id):
            raise ServiceError("NOT_FOUND", "未找到可处理的业务对象", status_code=404)
        if not idempotency_key or len(idempotency_key) > 128:
            raise ServiceError("VALIDATION_ERROR", "缺少有效的幂等标识")
        safe_payload = {k: v for k, v in payload.items() if k.lower() not in {"password", "code", "otp", "card_number"}}
        status, result, error_code = self.adapter.execute_self_service(
            capability, user_id=user_id, object_type=object_type,
            object_id=object_id, payload=safe_payload,
        )
        task, created = self.store.create_task(
            user_id=user_id, capability=capability, object_type=object_type,
            object_id=object_id, payload=safe_payload, idempotency_key=idempotency_key,
            status=status, result=result, error_code=error_code, data_mode=self.adapter.data_mode,
        )
        self.store.audit(
            actor_id=user_id, actor_role=Role.USER, action="self_service.start",
            resource_type="self_service_task", resource_id=task.id,
            result="created" if created else "deduplicated", trace_id=get_trace_id(),
            metadata={"capability": capability, "status": task.status.value},
        )
        return task, created

    def get_task(self, *, task_id: str, user_id: str, role: Role) -> SelfServiceTask:
        task = self.store.get_task(task_id, None if role in AGENT_ROLES else user_id)
        if not task:
            raise ServiceError("NOT_FOUND", "自助任务不存在", status_code=404)
        return task

    def create_ticket(
        self, *, user_id: str, session_id: str, category: str, title: str,
        description: str, object_data: dict, idempotency_key: str,
        actor_id: str | None = None, priority: str = "standard",
    ) -> tuple[SupportTicket, bool]:
        if not idempotency_key or len(idempotency_key) > 128:
            raise ServiceError("VALIDATION_ERROR", "缺少有效的幂等标识")
        safe_title, _ = sanitize_user_text(title[:120])
        safe_description, _ = sanitize_user_text(description[:5000])
        if not safe_title or not safe_description:
            raise ServiceError("VALIDATION_ERROR", "请填写问题标题和说明")
        ticket, created = self.store.create_ticket(
            user_id=user_id, session_id=session_id, category=category,
            title=safe_title, description=safe_description, priority=priority,
            object_data=object_data, idempotency_key=idempotency_key,
            actor_id=actor_id or user_id, data_mode=self.adapter.data_mode,
        )
        if created:
            sent = self.adapter.send_notification(
                user_id=user_id, event_type="ticket_created",
                content=f"服务记录 {ticket.id} 已创建",
            )
            self.store.add_notification(
                user_id=user_id, ticket_id=ticket.id, event_type="ticket_created",
                channel=sent["channel"], status=sent["status"],
                content="服务记录已创建，可在进度页面查看。", data_mode=sent["data_mode"],
            )
        self.store.audit(
            actor_id=actor_id or user_id, actor_role=Role.USER,
            action="ticket.create", resource_type="ticket", resource_id=ticket.id,
            result="created" if created else "deduplicated", trace_id=get_trace_id(),
            metadata={"category": category, "status": ticket.status.value},
        )
        return ticket, created

    def request_human(
        self, *, user_id: str, session_id: str, reason: str,
        summary: str, idempotency_key: str,
    ) -> QueueEntry:
        safe_summary = summarize_for_handoff(summary)
        # Service hours are not confirmed. Fail safely to an asynchronous ticket
        # instead of inventing an online queue position or wait duration.
        ticket, _ = self.create_ticket(
            user_id=user_id, session_id=session_id, category="人工服务",
            title="人工客服请求", description=safe_summary or "用户请求人工客服",
            object_data={"handoff_reason": reason}, idempotency_key=idempotency_key,
            priority="high" if reason == "high_risk" else "standard",
        )
        entry = self.store.create_queue(
            user_id=user_id, session_id=session_id, reason=reason,
            priority="high" if reason == "high_risk" else "standard",
            status=QueueStatus.ASYNC_TICKET, summary=safe_summary,
            ticket_id=ticket.id,
            service_message="人工在线时段尚未配置，本次问题已由异步工单承接。",
            data_mode=self.adapter.data_mode,
        )
        self.store.audit(
            actor_id=user_id, actor_role=Role.USER, action="queue.request",
            resource_type="queue_entry", resource_id=entry.id,
            result=entry.status.value, trace_id=get_trace_id(),
            metadata={"reason": reason, "ticket_id": ticket.id},
        )
        return entry

    def get_queue(self, *, queue_id: str, user_id: str, role: Role) -> QueueEntry:
        entry = self.store.get_queue(queue_id, None if role in AGENT_ROLES else user_id)
        if not entry:
            raise ServiceError("NOT_FOUND", "排队记录不存在", status_code=404)
        return entry

    def cancel_queue(self, *, queue_id: str, user_id: str) -> QueueEntry:
        entry = self.get_queue(queue_id=queue_id, user_id=user_id, role=Role.USER)
        if entry.status == QueueStatus.CANCELLED:
            return entry
        ensure_queue_transition(entry.status, QueueStatus.CANCELLED)
        return self.store.update_queue(queue_id, QueueStatus.CANCELLED)

    def list_tickets(self, *, user_id: str, role: Role) -> list[SupportTicket]:
        return self.store.list_tickets(None if role in AGENT_ROLES else user_id, include_internal=role in AGENT_ROLES)

    def get_ticket(self, *, ticket_id: str, user_id: str, role: Role) -> SupportTicket:
        ticket = self.store.get_ticket(ticket_id, None if role in AGENT_ROLES else user_id, include_internal=role in AGENT_ROLES)
        if not ticket:
            raise ServiceError("NOT_FOUND", "服务记录不存在", status_code=404)
        return ticket

    def add_comment(
        self, *, ticket_id: str, user_id: str, role: Role,
        content: str, visibility: str,
    ) -> TicketComment:
        self.get_ticket(ticket_id=ticket_id, user_id=user_id, role=role)
        if role not in AGENT_ROLES and visibility != "public":
            raise ServiceError("FORBIDDEN", "用户不能添加内部备注", status_code=403)
        safe_content, _ = sanitize_user_text(content[:3000])
        if not safe_content:
            raise ServiceError("VALIDATION_ERROR", "补充内容不能为空")
        return self.store.add_comment(
            ticket_id=ticket_id, author_id=user_id, author_role=role,
            content=safe_content, visibility=visibility,
        )

    def transition_ticket(
        self, *, ticket_id: str, user_id: str, role: Role,
        target: TicketStatus, reason: str,
    ) -> SupportTicket:
        ticket = self.get_ticket(ticket_id=ticket_id, user_id=user_id, role=role)
        if role not in AGENT_ROLES and target not in {TicketStatus.REOPENED, TicketStatus.CANCELLED}:
            raise ServiceError("FORBIDDEN", "用户无权执行该状态变更", status_code=403)
        ensure_ticket_transition(ticket.status, target)
        safe_reason, _ = sanitize_user_text(reason[:500])
        updated = self.store.transition_ticket(
            ticket_id=ticket.id, current=ticket.status, target=target,
            actor_id=user_id, reason=safe_reason,
        )
        sent = self.adapter.send_notification(
            user_id=ticket.user_id, event_type="ticket_status_changed",
            content=f"服务记录状态已更新为 {target.value}",
        )
        self.store.add_notification(
            user_id=ticket.user_id, ticket_id=ticket.id, event_type="ticket_status_changed",
            channel=sent["channel"], status=sent["status"],
            content=f"服务记录状态已更新：{target.value}", data_mode=sent["data_mode"],
        )
        self.store.audit(
            actor_id=user_id, actor_role=role, action="ticket.transition",
            resource_type="ticket", resource_id=ticket.id, result=target.value,
            trace_id=get_trace_id(), metadata={"from": ticket.status.value},
        )
        return updated

    def progress(self, user_id: str) -> dict[str, Any]:
        data = self.store.list_progress(user_id)
        data["tickets"] = [ticket.model_dump() for ticket in self.store.list_tickets(user_id)]
        return data

    def rate(
        self, *, user_id: str, service_type: str, service_id: str,
        resolved: bool, score: int | None, reason: str,
    ) -> tuple[Rating, bool]:
        if service_type == "ticket":
            self.get_ticket(ticket_id=service_id, user_id=user_id, role=Role.USER)
        safe_reason, _ = sanitize_user_text(reason[:500])
        rating, created = self.store.create_rating(
            user_id=user_id, service_type=service_type, service_id=service_id,
            resolved=resolved, score=score, reason=safe_reason,
        )
        if not resolved and service_type == "ticket":
            ticket = self.get_ticket(ticket_id=service_id, user_id=user_id, role=Role.USER)
            if ticket.status in {TicketStatus.RESOLVED_PENDING, TicketStatus.CLOSED}:
                self.transition_ticket(
                    ticket_id=service_id, user_id=user_id, role=Role.USER,
                    target=TicketStatus.REOPENED, reason=safe_reason or "用户确认仍未解决",
                )
        return rating, created

    def workspace(self, role: Role) -> dict[str, Any]:
        if role not in AGENT_ROLES:
            raise ServiceError("FORBIDDEN", "无权访问人工客服工作台", status_code=403)
        queues = self.store.list_queues(statuses=[QueueStatus.WAITING, QueueStatus.ASYNC_TICKET])
        tickets = self.store.list_tickets(include_internal=True)
        return {
            "queues": [item.model_dump() for item in queues],
            "tickets": [item.model_dump() for item in tickets],
            "data_mode": self.adapter.data_mode,
            "notice": "这是演示工作台，未连接真实坐席系统。",
        }

    def record_event(self, *, user_id: str, event_name: str, properties: dict) -> str:
        if event_name not in ALLOWED_EVENTS:
            raise ServiceError("VALIDATION_ERROR", "不支持的埋点事件")
        cleaned = {
            str(k)[:60]: str(v)[:300]
            for k, v in properties.items()
            if str(k).lower() not in {"message", "password", "code", "phone", "email", "address"}
        }
        return self.store.record_event(
            user_id=user_id, event_name=event_name,
            properties=cleaned, trace_id=get_trace_id(),
        )

    @staticmethod
    def deterministic_key(*parts: str) -> str:
        joined = "|".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


support_service = SupportService()
