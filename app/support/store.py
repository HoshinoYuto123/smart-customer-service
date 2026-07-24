"""SQLite persistence for support workflows.

All customer-owned reads include ``user_id``. PRD: CS-FN-005, CS-FN-007,
CS-FN-009 through CS-FN-012, CS-BR-008, CS-BR-014 through CS-BR-020.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.session_store import DB_PATH
from app.support.models import (
    QueueEntry,
    QueueStatus,
    Rating,
    Role,
    SelfServiceStatus,
    SelfServiceTask,
    SupportTicket,
    TicketComment,
    TicketHistory,
    TicketStatus,
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class SupportStore:
    def _connect(self) -> sqlite3.Connection:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db(self) -> None:
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS self_service_tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                object_type TEXT NOT NULL DEFAULT '',
                object_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                input_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error_code TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL,
                data_mode TEXT NOT NULL DEFAULT 'mock',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, capability, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_self_tasks_owner_status
                ON self_service_tasks(user_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS queue_entries (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'standard',
                status TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                ticket_id TEXT NOT NULL DEFAULT '',
                service_message TEXT NOT NULL DEFAULT '',
                data_mode TEXT NOT NULL DEFAULT 'mock',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_queue_owner_status
                ON queue_entries(user_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS support_tickets (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'standard',
                object_json TEXT NOT NULL DEFAULT '{}',
                idempotency_key TEXT NOT NULL,
                data_mode TEXT NOT NULL DEFAULT 'mock',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                UNIQUE(user_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_owner_status
                ON support_tickets(user_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS ticket_comments (
                id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_role TEXT NOT NULL,
                content TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'public',
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES support_tickets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_ticket_comments
                ON ticket_comments(ticket_id, created_at);

            CREATE TABLE IF NOT EXISTS ticket_status_history (
                id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                from_status TEXT NOT NULL DEFAULT '',
                to_status TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES support_tickets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_ticket_history
                ON ticket_status_history(ticket_id, created_at);

            CREATE TABLE IF NOT EXISTS support_notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                content TEXT NOT NULL,
                data_mode TEXT NOT NULL DEFAULT 'mock',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS satisfaction_ratings (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                service_type TEXT NOT NULL,
                service_id TEXT NOT NULL,
                resolved INTEGER NOT NULL,
                score INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, service_type, service_id)
            );

            CREATE TABLE IF NOT EXISTS faq_feedback (
                id TEXT PRIMARY KEY,
                article_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                resolved INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(article_id, user_id, session_id)
            );

            CREATE TABLE IF NOT EXISTS support_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_name TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                trace_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                result TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_resource
                ON audit_logs(resource_type, resource_id, created_at DESC);
        """)
        conn.commit()
        conn.close()

    @staticmethod
    def _task(row: sqlite3.Row) -> SelfServiceTask:
        return SelfServiceTask(
            id=row["id"], user_id=row["user_id"], capability=row["capability"],
            object_type=row["object_type"], object_id=row["object_id"],
            status=SelfServiceStatus(row["status"]), input=_loads(row["input_json"], {}),
            result=_loads(row["result_json"], {}), error_code=row["error_code"],
            idempotency_key=row["idempotency_key"], data_mode=row["data_mode"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def create_task(
        self, *, user_id: str, capability: str, object_type: str, object_id: str,
        payload: dict, idempotency_key: str, status: SelfServiceStatus,
        result: dict, error_code: str, data_mode: str,
    ) -> tuple[SelfServiceTask, bool]:
        conn = self._connect()
        now = utcnow()
        task_id = new_id("TASK")
        created = True
        try:
            conn.execute(
                "INSERT INTO self_service_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, user_id, capability, object_type, object_id, status.value,
                 _json(payload), _json(result), error_code, idempotency_key, data_mode, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            created = False
            conn.rollback()
        row = conn.execute(
            "SELECT * FROM self_service_tasks WHERE user_id=? AND capability=? AND idempotency_key=?",
            (user_id, capability, idempotency_key),
        ).fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("self-service task was not persisted")
        return self._task(row), created

    def get_task(self, task_id: str, user_id: str | None = None) -> SelfServiceTask | None:
        conn = self._connect()
        if user_id is None:
            row = conn.execute("SELECT * FROM self_service_tasks WHERE id=?", (task_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM self_service_tasks WHERE id=? AND user_id=?", (task_id, user_id)).fetchone()
        conn.close()
        return self._task(row) if row else None

    @staticmethod
    def _queue(row: sqlite3.Row) -> QueueEntry:
        return QueueEntry(
            id=row["id"], session_id=row["session_id"], user_id=row["user_id"],
            reason=row["reason"], priority=row["priority"], status=QueueStatus(row["status"]),
            summary=row["summary"], ticket_id=row["ticket_id"], service_message=row["service_message"],
            data_mode=row["data_mode"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def create_queue(
        self, *, user_id: str, session_id: str, reason: str, priority: str,
        status: QueueStatus, summary: str, ticket_id: str = "", service_message: str = "",
        data_mode: str = "mock",
    ) -> QueueEntry:
        conn = self._connect()
        now = utcnow()
        queue_id = new_id("QUEUE")
        conn.execute(
            "INSERT INTO queue_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (queue_id, session_id, user_id, reason, priority, status.value, summary,
             ticket_id, service_message, data_mode, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM queue_entries WHERE id=?", (queue_id,)).fetchone()
        conn.close()
        return self._queue(row)

    def get_queue(self, queue_id: str, user_id: str | None = None) -> QueueEntry | None:
        conn = self._connect()
        if user_id is None:
            row = conn.execute("SELECT * FROM queue_entries WHERE id=?", (queue_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM queue_entries WHERE id=? AND user_id=?", (queue_id, user_id)).fetchone()
        conn.close()
        return self._queue(row) if row else None

    def update_queue(self, queue_id: str, target: QueueStatus) -> QueueEntry:
        conn = self._connect()
        conn.execute("UPDATE queue_entries SET status=?, updated_at=? WHERE id=?", (target.value, utcnow(), queue_id))
        conn.commit()
        row = conn.execute("SELECT * FROM queue_entries WHERE id=?", (queue_id,)).fetchone()
        conn.close()
        if not row:
            raise KeyError(queue_id)
        return self._queue(row)

    def list_queues(self, *, statuses: list[QueueStatus] | None = None, limit: int = 50) -> list[QueueEntry]:
        conn = self._connect()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            rows = conn.execute(
                f"SELECT * FROM queue_entries WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?",
                (*[s.value for s in statuses], limit),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM queue_entries ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [self._queue(row) for row in rows]

    @staticmethod
    def _comment(row: sqlite3.Row) -> TicketComment:
        return TicketComment(
            id=row["id"], ticket_id=row["ticket_id"], author_id=row["author_id"],
            author_role=Role(row["author_role"]), content=row["content"],
            visibility=row["visibility"], created_at=row["created_at"],
        )

    @staticmethod
    def _history(row: sqlite3.Row) -> TicketHistory:
        return TicketHistory(
            id=row["id"], ticket_id=row["ticket_id"], from_status=row["from_status"],
            to_status=TicketStatus(row["to_status"]), actor_id=row["actor_id"],
            reason=row["reason"], created_at=row["created_at"],
        )

    def _ticket(self, conn: sqlite3.Connection, row: sqlite3.Row, *, include_internal: bool = False) -> SupportTicket:
        comment_sql = "SELECT * FROM ticket_comments WHERE ticket_id=?"
        params: tuple[Any, ...] = (row["id"],)
        if not include_internal:
            comment_sql += " AND visibility='public'"
        comment_sql += " ORDER BY created_at"
        comments = [self._comment(item) for item in conn.execute(comment_sql, params).fetchall()]
        history = [self._history(item) for item in conn.execute(
            "SELECT * FROM ticket_status_history WHERE ticket_id=? ORDER BY created_at", (row["id"],)
        ).fetchall()]
        return SupportTicket(
            id=row["id"], user_id=row["user_id"], session_id=row["session_id"],
            category=row["category"], title=row["title"], description=row["description"],
            status=TicketStatus(row["status"]), priority=row["priority"],
            object=_loads(row["object_json"], {}), idempotency_key=row["idempotency_key"],
            data_mode=row["data_mode"], created_at=row["created_at"], updated_at=row["updated_at"],
            comments=comments, history=history,
        )

    def create_ticket(
        self, *, user_id: str, session_id: str, category: str, title: str,
        description: str, priority: str, object_data: dict, idempotency_key: str,
        actor_id: str, data_mode: str = "mock",
    ) -> tuple[SupportTicket, bool]:
        conn = self._connect()
        now = utcnow()
        ticket_id = new_id("TICKET")
        created = True
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO support_tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (ticket_id, user_id, session_id, category, title, description,
                 TicketStatus.SUBMITTED.value, priority, _json(object_data),
                 idempotency_key, data_mode, now, now),
            )
            conn.execute(
                "INSERT INTO ticket_status_history VALUES (?,?,?,?,?,?,?)",
                (new_id("HIST"), ticket_id, "", TicketStatus.SUBMITTED.value, actor_id, "工单已提交", now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            created = False
            conn.rollback()
        row = conn.execute(
            "SELECT * FROM support_tickets WHERE user_id=? AND idempotency_key=? AND deleted_at IS NULL",
            (user_id, idempotency_key),
        ).fetchone()
        if row is None:
            conn.close()
            raise RuntimeError("ticket was not persisted")
        ticket = self._ticket(conn, row)
        conn.close()
        return ticket, created

    def get_ticket(self, ticket_id: str, user_id: str | None = None, *, include_internal: bool = False) -> SupportTicket | None:
        conn = self._connect()
        if user_id is None:
            row = conn.execute("SELECT * FROM support_tickets WHERE id=? AND deleted_at IS NULL", (ticket_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM support_tickets WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (ticket_id, user_id),
            ).fetchone()
        ticket = self._ticket(conn, row, include_internal=include_internal) if row else None
        conn.close()
        return ticket

    def list_tickets(self, user_id: str | None = None, *, include_internal: bool = False, limit: int = 50) -> list[SupportTicket]:
        conn = self._connect()
        if user_id is None:
            rows = conn.execute(
                "SELECT * FROM support_tickets WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM support_tickets WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        tickets = [self._ticket(conn, row, include_internal=include_internal) for row in rows]
        conn.close()
        return tickets

    def add_comment(
        self, *, ticket_id: str, author_id: str, author_role: Role,
        content: str, visibility: str,
    ) -> TicketComment:
        conn = self._connect()
        comment_id = new_id("COMMENT")
        now = utcnow()
        conn.execute(
            "INSERT INTO ticket_comments VALUES (?,?,?,?,?,?,?)",
            (comment_id, ticket_id, author_id, author_role.value, content, visibility, now),
        )
        conn.execute("UPDATE support_tickets SET updated_at=? WHERE id=?", (now, ticket_id))
        conn.commit()
        row = conn.execute("SELECT * FROM ticket_comments WHERE id=?", (comment_id,)).fetchone()
        conn.close()
        return self._comment(row)

    def transition_ticket(
        self, *, ticket_id: str, current: TicketStatus, target: TicketStatus,
        actor_id: str, reason: str,
    ) -> SupportTicket:
        conn = self._connect()
        now = utcnow()
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                "UPDATE support_tickets SET status=?, updated_at=? WHERE id=? AND status=?",
                (target.value, now, ticket_id, current.value),
            ).rowcount
            if changed != 1:
                raise RuntimeError("ticket state changed concurrently")
            conn.execute(
                "INSERT INTO ticket_status_history VALUES (?,?,?,?,?,?,?)",
                (new_id("HIST"), ticket_id, current.value, target.value, actor_id, reason, now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            raise
        row = conn.execute("SELECT * FROM support_tickets WHERE id=?", (ticket_id,)).fetchone()
        ticket = self._ticket(conn, row, include_internal=True)
        conn.close()
        return ticket

    def upsert_faq_feedback(
        self, *, article_id: str, user_id: str, session_id: str, resolved: bool, reason: str,
    ) -> dict:
        conn = self._connect()
        now = utcnow()
        feedback_id = new_id("FAQFB")
        conn.execute(
            "INSERT INTO faq_feedback VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(article_id,user_id,session_id) DO UPDATE SET resolved=excluded.resolved, reason=excluded.reason, updated_at=excluded.updated_at",
            (feedback_id, article_id, user_id, session_id, int(resolved), reason, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM faq_feedback WHERE article_id=? AND user_id=? AND session_id=?",
            (article_id, user_id, session_id),
        ).fetchone()
        conn.close()
        return dict(row)

    def create_rating(
        self, *, user_id: str, service_type: str, service_id: str,
        resolved: bool, score: int | None, reason: str,
    ) -> tuple[Rating, bool]:
        conn = self._connect()
        now = utcnow()
        rating_id = new_id("RATING")
        created = True
        try:
            conn.execute(
                "INSERT INTO satisfaction_ratings VALUES (?,?,?,?,?,?,?,?)",
                (rating_id, user_id, service_type, service_id, int(resolved), score, reason, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            created = False
            conn.rollback()
        row = conn.execute(
            "SELECT * FROM satisfaction_ratings WHERE user_id=? AND service_type=? AND service_id=?",
            (user_id, service_type, service_id),
        ).fetchone()
        conn.close()
        return Rating(
            id=row["id"], user_id=row["user_id"], service_type=row["service_type"],
            service_id=row["service_id"], resolved=bool(row["resolved"]), score=row["score"],
            reason=row["reason"], created_at=row["created_at"],
        ), created

    def add_notification(
        self, *, user_id: str, ticket_id: str, event_type: str,
        channel: str, status: str, content: str, data_mode: str,
    ) -> str:
        conn = self._connect()
        notification_id = new_id("NOTICE")
        now = utcnow()
        conn.execute(
            "INSERT INTO support_notifications VALUES (?,?,?,?,?,?,?,?,?,?)",
            (notification_id, user_id, ticket_id, event_type, channel, status, content, data_mode, now, now),
        )
        conn.commit()
        conn.close()
        return notification_id

    def list_progress(self, user_id: str) -> dict[str, list[dict]]:
        conn = self._connect()
        tasks = [dict(row) for row in conn.execute(
            "SELECT id,capability,object_type,object_id,status,result_json,error_code,data_mode,created_at,updated_at "
            "FROM self_service_tasks WHERE user_id=? ORDER BY updated_at DESC LIMIT 30", (user_id,)
        ).fetchall()]
        queues = [dict(row) for row in conn.execute(
            "SELECT id,session_id,reason,status,ticket_id,service_message,data_mode,created_at,updated_at "
            "FROM queue_entries WHERE user_id=? ORDER BY updated_at DESC LIMIT 30", (user_id,)
        ).fetchall()]
        notices = [dict(row) for row in conn.execute(
            "SELECT id,ticket_id,event_type,channel,status,content,data_mode,created_at,updated_at "
            "FROM support_notifications WHERE user_id=? ORDER BY updated_at DESC LIMIT 30", (user_id,)
        ).fetchall()]
        conn.close()
        for task in tasks:
            task["result"] = _loads(task.pop("result_json", "{}"), {})
        return {"tasks": tasks, "queues": queues, "notifications": notices}

    def record_event(self, *, user_id: str, event_name: str, properties: dict, trace_id: str) -> str:
        conn = self._connect()
        event_id = new_id("EVENT")
        conn.execute(
            "INSERT INTO support_events VALUES (?,?,?,?,?,?)",
            (event_id, user_id, event_name, _json(properties), trace_id, utcnow()),
        )
        conn.commit()
        conn.close()
        return event_id

    def audit(
        self, *, actor_id: str, actor_role: Role, action: str, resource_type: str,
        resource_id: str, result: str, trace_id: str = "", metadata: dict | None = None,
    ) -> str:
        conn = self._connect()
        audit_id = new_id("AUDIT")
        conn.execute(
            "INSERT INTO audit_logs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (audit_id, actor_id, actor_role.value, action, resource_type, resource_id,
             result, trace_id, _json(metadata or {}), utcnow()),
        )
        conn.commit()
        conn.close()
        return audit_id


support_store = SupportStore()
support_store.init_db()
