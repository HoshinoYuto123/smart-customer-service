"""Session manager backed by SQLite persistent storage."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.types import SessionContext
from app.core import session_store
from app.core.observability import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages user sessions with SQLite persistence."""

    async def get_or_create(self, session_id: str, user_id: str = "", channel: str = "web") -> SessionContext:
        session = session_store.get_session(session_id)
        if session:
            session_store.touch_session(session_id)
        else:
            session = session_store.create_session(session_id, user_id, channel)

        history = session_store.get_messages(session_id)
        clarify_count = sum(1 for m in history if m["role"] == "assistant" and "请问" in m["content"])

        return SessionContext(
            session_id=session_id,
            user_id=session.get("user_id", user_id),
            channel=session.get("channel", channel),
            clarify_count=clarify_count,
            current_domain="",
            history=history,
            created_at=session.get("created_at", ""),
            updated_at=session.get("updated_at", ""),
        )

    async def add_history(self, session_id: str, role: str, content: str, metadata: dict | None = None):
        if content:
            session_store.add_message(session_id, role, content)
        # Auto-set title from first user message
        if role == "user":
            session_store.update_session_title(session_id, content)

    async def get_history(self, session_id: str, token_limit: int = 3000) -> list[dict]:
        return session_store.get_messages(session_id, token_limit)

    async def increment_clarify_count(self, session_id: str) -> int:
        history = session_store.get_messages(session_id)
        count = sum(1 for m in history if m["role"] == "assistant" and "请问" in m["content"])
        return count + 1

    async def reset_clarify_count(self, session_id: str):
        pass  # Clarify count is derived from history

    async def set_domain(self, session_id: str, domain: str):
        pass  # Domain stored implicitly in history

    async def delete(self, session_id: str):
        session_store.delete_session(session_id)

    async def cleanup_expired(self):
        pass  # SQLite doesn't need TTL cleanup


session_manager = SessionManager()
