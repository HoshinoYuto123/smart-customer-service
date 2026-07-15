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
    conn.commit()
    conn.close()


def create_session(session_id: str, user_id: str = "", channel: str = "web") -> dict:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, title, user_id, channel, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, "", user_id, channel, now, now),
    )
    conn.commit()
    conn.close()
    return get_session(session_id)


def get_session(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_sessions(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM messages WHERE session_id = s.id) as msg_count "
        "FROM sessions s ORDER BY updated_at DESC LIMIT ?",
        (limit,),
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
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
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


def delete_session(session_id: str):
    conn = _get_conn()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# Initialize on import
init_db()
