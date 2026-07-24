"""Session manager backed by SQLite persistent storage."""

from __future__ import annotations

import asyncio
import weakref
from contextlib import asynccontextmanager

from app.agent.types import SessionContext
from app.core import session_store
from app.core.observability import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages user sessions with SQLite persistence."""

    def __init__(self) -> None:
        self._turn_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    @asynccontextmanager
    async def turn_lock(self, session_id: str):
        lock = self._turn_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            yield

    async def get_or_create(self, session_id: str, user_id: str = "", channel: str = "web") -> SessionContext:
        session = await asyncio.to_thread(session_store.get_session, session_id)
        if session:
            if session.get("user_id") not in ("", user_id):
                raise PermissionError("session belongs to another user")
            if not session.get("user_id"):
                session = await asyncio.to_thread(session_store.create_session, session_id, user_id, channel)
            await asyncio.to_thread(session_store.touch_session, session_id)
        else:
            session = await asyncio.to_thread(session_store.create_session, session_id, user_id, channel)

        history = await asyncio.to_thread(session_store.get_messages, session_id)

        return SessionContext(
            session_id=session_id,
            user_id=session.get("user_id", user_id),
            channel=session.get("channel", channel),
            clarify_count=session.get("clarify_count", 0),
            unresolved_count=session.get("unresolved_count", 0),
            current_domain=session.get("current_domain", ""),
            history=history,
            created_at=session.get("created_at", ""),
            updated_at=session.get("updated_at", ""),
        )

    async def add_history(self, session_id: str, role: str, content: str, metadata: dict | None = None):
        if content:
            await asyncio.to_thread(session_store.add_message, session_id, role, content)
        # Auto-set title from first user message
        if role == "user":
            await asyncio.to_thread(session_store.update_session_title, session_id, content)

    async def get_history(self, session_id: str, token_limit: int = 3000) -> list[dict]:
        return await asyncio.to_thread(session_store.get_messages, session_id, token_limit)

    async def increment_clarify_count(self, session_id: str) -> int:
        session = await asyncio.to_thread(session_store.get_session, session_id)
        count = int(session.get("clarify_count", 0)) + 1 if session else 1
        await asyncio.to_thread(session_store.update_session_state, session_id, clarify_count=count)
        return count

    async def reset_clarify_count(self, session_id: str):
        await asyncio.to_thread(session_store.update_session_state, session_id, clarify_count=0)

    async def set_domain(self, session_id: str, domain: str):
        await asyncio.to_thread(session_store.update_session_state, session_id, current_domain=domain)

    async def set_state(self, session_id: str, *, clarify_count: int, current_domain: str):
        await asyncio.to_thread(
            session_store.update_session_state,
            session_id,
            clarify_count=clarify_count,
            current_domain=current_domain,
        )

    async def record_turn(
        self,
        session_id: str,
        *,
        user_content: str,
        assistant_content: str,
        clarify_count: int,
        current_domain: str,
        unresolved_count: int = 0,
    ) -> None:
        await asyncio.to_thread(
            session_store.record_turn,
            session_id,
            user_content=user_content,
            assistant_content=assistant_content,
            clarify_count=clarify_count,
            unresolved_count=unresolved_count,
            current_domain=current_domain,
        )

    async def delete(self, session_id: str):
        await asyncio.to_thread(session_store.delete_session, session_id)
        self._turn_locks.pop(session_id, None)

    async def cleanup_expired(self):
        pass  # SQLite doesn't need TTL cleanup


session_manager = SessionManager()
