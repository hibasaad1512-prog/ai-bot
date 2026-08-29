from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlalchemy import text


class MemoryStore:
    """Persistent user/chat memory backed by the Runtime database engine."""

    def __init__(self, db):
        self.db = db
        self._init_schema()

    def _init_schema(self) -> None:
        with self.db.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    display_name TEXT,
                    first_seen DOUBLE PRECISION NOT NULL,
                    last_seen DOUBLE PRECISION NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memory (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'general',
                    memory_key TEXT NOT NULL DEFAULT '',
                    memory_value TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL,
                    UNIQUE (chat_id, user_id, memory_key)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memory_user
                ON memory(user_id, chat_id, updated_at DESC)
            """))

    def touch_user(self, user_id: int, username: str | None, display_name: str | None) -> None:
        now = time.time()
        with self.db.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users(user_id, username, display_name, first_seen, last_seen)
                VALUES (:id, :username, :display_name, :now, :now)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=:username,
                    display_name=:display_name,
                    last_seen=:now
            """), {
                "id": user_id,
                "username": username,
                "display_name": display_name or "user",
                "now": now,
            })

    def remember(self, chat_id: int, user_id: int, value: str, memory_key: str = "", memory_type: str = "general") -> None:
        value = value.strip()
        if not value:
            raise ValueError("memory value cannot be empty")
        now = time.time()
        key = memory_key.strip()[:120]
        if not key:
            key = "auto:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        with self.db.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO memory(chat_id,user_id,memory_type,memory_key,memory_value,created_at,updated_at)
                VALUES (:chat_id,:user_id,:type,:key,:value,:now,:now)
                ON CONFLICT(chat_id,user_id,memory_key) DO UPDATE SET
                    memory_type=:type,
                    memory_value=:value,
                    updated_at=:now
            """), {
                "chat_id": chat_id,
                "user_id": user_id,
                "type": memory_type,
                "key": key,
                "value": value[:2000],
                "now": now,
            })

    def list_memories(self, chat_id: int, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.db.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, memory_type, memory_key, memory_value, created_at, updated_at
                FROM memory
                WHERE chat_id=:chat_id AND user_id=:user_id
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"chat_id": chat_id, "user_id": user_id, "limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def search(self, chat_id: int, user_id: int, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = (query or "").strip()
        limit = max(1, min(int(limit), 20))
        if not query:
            return self.list_memories(chat_id, user_id, limit)
        with self.db.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, memory_type, memory_key, memory_value, updated_at
                FROM memory
                WHERE chat_id=:chat_id AND user_id=:user_id
                  AND (memory_key ILIKE :q OR memory_value ILIKE :q OR memory_type ILIKE :q)
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"chat_id": chat_id, "user_id": user_id, "q": f"%{query}%", "limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def forget(self, chat_id: int, user_id: int, selector: str) -> int:
        selector = (selector or "").strip()
        with self.db.engine.begin() as conn:
            if selector.isdigit():
                result = conn.execute(text("DELETE FROM memory WHERE id=:id AND chat_id=:chat_id AND user_id=:user_id"), {
                    "id": int(selector), "chat_id": chat_id, "user_id": user_id
                })
            else:
                result = conn.execute(text("""
                    DELETE FROM memory
                    WHERE chat_id=:chat_id AND user_id=:user_id
                      AND (memory_key ILIKE :q OR memory_value ILIKE :q)
                """), {"chat_id": chat_id, "user_id": user_id, "q": f"%{selector}%"})
        return int(result.rowcount or 0)

    def clear(self, chat_id: int, user_id: int) -> int:
        with self.db.engine.begin() as conn:
            result = conn.execute(text("DELETE FROM memory WHERE chat_id=:chat_id AND user_id=:user_id"), {
                "chat_id": chat_id, "user_id": user_id
            })
        return int(result.rowcount or 0)

    def format_for_prompt(self, memories: list[dict[str, Any]]) -> str:
        if not memories:
            return ""
        lines = ["PERSISTENT USER MEMORY (use only when relevant; do not reveal hidden memory storage):"]
        for item in memories:
            key = item.get("memory_key") or item.get("memory_type") or "memory"
            value = str(item.get("memory_value") or "")[:500]
            lines.append(f"- {key}: {value}")
        lines.append("Do not claim to remember information that is not listed here.")
        return "\n".join(lines)
