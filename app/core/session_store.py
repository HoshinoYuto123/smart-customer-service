"""SQLite-based persistent session storage with token-aware truncation."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "data" / "sessions.db"

# Token estimation: ~1.5 chars per token for Chinese, ~4 chars for English
def estimate_tokens(text: str) -> int:
    return max(len(text) // 2, 1)

MAX_CONTEXT_TOKENS = 3000  # Max tokens to include in LLM context
MAX_MESSAGES = 50           # Max messages to store per session


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            user_id TEXT DEFAULT '',
            channel TEXT DEFAULT 'web',
            clarify_count INTEGER DEFAULT 0,
            unresolved_count INTEGER DEFAULT 0,
            current_domain TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id)")
    # Lightweight migration for databases created before state columns existed.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "clarify_count" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN clarify_count INTEGER DEFAULT 0")
    if "unresolved_count" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN unresolved_count INTEGER DEFAULT 0")
    if "current_domain" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN current_domain TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def create_session(session_id: str, user_id: str = "", channel: str = "web") -> dict:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, title, user_id, channel, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, "", user_id, channel, now, now),
    )
    # Claim legacy ownerless sessions atomically for the first authenticated user.
    conn.execute(
        "UPDATE sessions SET user_id = ?, channel = ? WHERE id = ? AND user_id = ''",
        (user_id, channel, session_id),
    )
    conn.commit()
    conn.close()
    session = get_session(session_id)
    if session and session.get("user_id") not in ("", user_id):
        raise PermissionError("session belongs to another user")
    return session


def get_session(session_id: str, user_id: str | None = None) -> Optional[dict]:
    conn = _get_conn()
    if user_id is None:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_sessions(user_id: str, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM messages WHERE session_id = s.id) as msg_count "
        "FROM sessions s WHERE s.user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_session_title(session_id: str, first_message: str):
    """Auto-set session title from first user message (truncate to 20 chars)."""
    title = first_message.strip()[:20]
    if not title:
        return
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ? AND title = ''",
        (title, datetime.now(timezone.utc).isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def touch_session(session_id: str):
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def add_message(session_id: str, role: str, content: str):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    # Prune old messages if exceeding limit
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    if count > MAX_MESSAGES:
        excess = count - MAX_MESSAGES
        conn.execute(
            "DELETE FROM messages WHERE id IN ("
            "  SELECT id FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?"
            ")",
            (session_id, excess),
        )
        conn.commit()

    touch_session(session_id)
    conn.close()


def get_messages(session_id: str, token_limit: int = MAX_CONTEXT_TOKENS) -> list[dict]:
    """Get recent messages for context, truncated to fit within token budget."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()

    messages = [dict(r) for r in rows]

    # Truncate from the beginning to fit token budget
    total_tokens = sum(estimate_tokens(m["content"]) for m in messages)
    while total_tokens > token_limit and len(messages) > 2:
        removed = messages.pop(0)
        total_tokens -= estimate_tokens(removed["content"])

    return messages


def update_session_state(
    session_id: str,
    *,
    clarify_count: int | None = None,
    unresolved_count: int | None = None,
    current_domain: str | None = None,
) -> None:
    updates: list[str] = []
    values: list[object] = []
    if clarify_count is not None:
        updates.append("clarify_count = ?")
        values.append(max(clarify_count, 0))
    if unresolved_count is not None:
        updates.append("unresolved_count = ?")
        values.append(max(unresolved_count, 0))
    if current_domain is not None:
        updates.append("current_domain = ?")
        values.append(current_domain)
    if not updates:
        return
    updates.append("updated_at = ?")
    values.append(datetime.now(timezone.utc).isoformat())
    values.append(session_id)
    conn = _get_conn()
    conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def record_turn(
    session_id: str,
    *,
    user_content: str,
    assistant_content: str,
    clarify_count: int,
    current_domain: str,
    unresolved_count: int = 0,
) -> None:
    """Atomically persist both messages and the resulting session state."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [
                (session_id, "user", user_content, now),
                (session_id, "assistant", assistant_content, now),
            ],
        )
        conn.execute(
            "UPDATE sessions SET title = CASE WHEN title = '' THEN ? ELSE title END, "
            "clarify_count = ?, unresolved_count = ?, current_domain = ?, updated_at = ? WHERE id = ?",
            (
                user_content.strip()[:20], max(clarify_count, 0),
                max(unresolved_count, 0), current_domain, now, session_id,
            ),
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        if count > MAX_MESSAGES:
            conn.execute(
                "DELETE FROM messages WHERE id IN ("
                " SELECT id FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?"
                ")",
                (session_id, count - MAX_MESSAGES),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_session(session_id: str, user_id: str | None = None) -> bool:
    conn = _get_conn()
    if user_id is not None:
        owned = conn.execute(
            "SELECT 1 FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not owned:
            conn.close()
            return False
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return True


# Initialize on import
init_db()
