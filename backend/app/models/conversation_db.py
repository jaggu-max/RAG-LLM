"""SQLite database manager for storing conversations and chat history."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _get_db_path() -> str:
    db_path = settings.CONVERSATIONS_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_conversation_db() -> None:
    """Initialize conversations and messages SQLite tables."""
    db_path = _get_db_path()
    log.info("Initializing conversation SQLite database at %s", db_path)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                answer_type TEXT,
                confidence REAL,
                sources TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
            );
        """)
        try:
            cursor.execute("ALTER TABLE messages ADD COLUMN sources TEXT;")
        except Exception:
            pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages (conversation_id);")
        conn.commit()


def create_conversation(title: str = "New Conversation", conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a new conversation entry."""
    cid = conversation_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now)
        )
        conn.commit()
    return {"id": cid, "title": title, "created_at": now, "updated_at": now, "messages": []}


def list_conversations() -> List[Dict[str, Any]]:
    """List all conversations ordered by updated_at descending."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Get a conversation by ID along with its full message history."""
    import json
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (conversation_id,))
        conv_row = cursor.fetchone()
        if not conv_row:
            return None

        conv = dict(conv_row)
        cursor.execute("""
            SELECT id, conversation_id, role, content, model, answer_type, confidence, sources, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """, (conversation_id,))
        msg_rows = cursor.fetchall()
        messages = []
        for r in msg_rows:
            d = dict(r)
            if d.get("sources"):
                try:
                    d["sources"] = json.loads(d["sources"]) if isinstance(d["sources"], str) else d["sources"]
                except Exception:
                    d["sources"] = []
            else:
                d["sources"] = []
            messages.append(d)
        conv["messages"] = messages
        return conv


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation and all its messages."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return cursor.rowcount > 0


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    model: str = "",
    answer_type: str = "",
    confidence: float = 0.0,
    sources: Optional[Any] = None,
) -> Dict[str, Any]:
    """Add a message to a conversation and update the conversation timestamp and title if needed."""
    import json
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources) if sources is not None and not isinstance(sources, str) else (sources or "")
    with get_connection() as conn:
        cursor = conn.cursor()
        # Ensure conversation exists
        cursor.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        if not row:
            title = content[:35] + "..." if len(content) > 35 else (content or "New Conversation")
            cursor.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title, now, now)
            )
        else:
            # Update title if it's default
            current_title = row["title"]
            if current_title == "New Conversation" and role == "user" and content:
                new_title = content[:35] + "..." if len(content) > 35 else content
                cursor.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (new_title, now, conversation_id)
                )
            else:
                cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))

        cursor.execute("""
            INSERT INTO messages (id, conversation_id, role, content, model, answer_type, confidence, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, conversation_id, role, content, model, answer_type, confidence, sources_json, now))
        conn.commit()

    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "model": model,
        "answer_type": answer_type,
        "confidence": confidence,
        "created_at": now,
    }


def get_recent_messages(conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve the most recent N messages for conversation context."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content
            FROM (
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            ORDER BY created_at ASC
        """, (conversation_id, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
