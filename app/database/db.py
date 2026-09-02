from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.models import ChatMessage

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS chat_settings (chat_id BIGINT PRIMARY KEY, settings_json TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS points (chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL, points INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, games_played INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (chat_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS chat_state (chat_id BIGINT PRIMARY KEY, state_json TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS chat_messages (chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL, user_id BIGINT NOT NULL, display_name TEXT NOT NULL DEFAULT '', timestamp DOUBLE PRECISION NOT NULL, text TEXT NOT NULL DEFAULT '', reply_to_message_id BIGINT, media_type TEXT, image_file_id TEXT, is_bot BOOLEAN NOT NULL DEFAULT FALSE, PRIMARY KEY (chat_id, message_id))""",
    """CREATE INDEX IF NOT EXISTS idx_chat_messages_recent ON chat_messages(chat_id, timestamp DESC)""",
    """CREATE TABLE IF NOT EXISTS media_pool (chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL, telegram_file_id TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, used_at DOUBLE PRECISION, uploader_id BIGINT NOT NULL DEFAULT 0, media_type TEXT NOT NULL, PRIMARY KEY (chat_id, telegram_file_id))""",
    """CREATE INDEX IF NOT EXISTS idx_media_pool_chat ON media_pool(chat_id, created_at DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_media_pool_used ON media_pool(chat_id, used_at)""",
]

_MESSAGE_WRITER = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db-msg")


def normalize_database_url(url: str) -> str:
    if not url:
        return "sqlite:////tmp/kyoos.sqlite3"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Database:
    def __init__(self, url: str):
        self.url = normalize_database_url(url)
        self.engine: Engine = create_engine(self.url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)
        self.init()

    def init(self) -> None:
        with self.engine.begin() as conn:
            for stmt in SCHEMA:
                conn.execute(text(stmt))
        self.prune_stale_storage()

    def get_json(self, table: str, key_col: str, key: int, default: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(text(f"SELECT * FROM {table} WHERE {key_col}=:key"), {"key": key}).mappings().first()
        if not row:
            return default or {}
        try:
            return json.loads(row.get("settings_json") or row.get("state_json") or "{}")
        except Exception:
            return default or {}

    def save_chat_settings(self, chat_id: int, payload: dict[str, Any]) -> None:
        # Root settings are shared by multiple subsystems; merge instead of letting
        # one subsystem accidentally erase another subsystem's settings.
        if int(chat_id) == 0:
            current = self.get_json("chat_settings", "chat_id", 0, {})
            if isinstance(current, dict):
                merged = dict(current)
                merged.update(payload)
                payload = merged
        self._save_json("chat_settings", "settings_json", chat_id, payload)

    def save_state(self, chat_id: int, payload: dict[str, Any]) -> None:
        self._save_json("chat_state", "state_json", chat_id, payload)

    def _save_json(self, table: str, column: str, chat_id: int, payload: dict[str, Any]) -> None:
        now = time.time(); raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.engine.begin() as conn:
            conn.execute(text(f"""INSERT INTO {table}(chat_id,{column},updated_at) VALUES (:id,:raw,:ts)
                ON CONFLICT(chat_id) DO UPDATE SET {column}=:raw, updated_at=:ts"""), {"id": chat_id, "raw": raw, "ts": now})

    def save_message(self, message: ChatMessage) -> None:
        payload = message.as_dict()
        try:
            _MESSAGE_WRITER.submit(self._save_message_sync, payload)
        except Exception:
            pass

    def _save_message_sync(self, payload: dict[str, Any]) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""INSERT INTO chat_messages(chat_id,message_id,user_id,display_name,timestamp,text,reply_to_message_id,media_type,image_file_id,is_bot)
                    VALUES(:chat_id,:message_id,:user_id,:display_name,:timestamp,:text,:reply_to_message_id,:media_type,:image_file_id,:is_bot)
                    ON CONFLICT(chat_id,message_id) DO UPDATE SET user_id=:user_id,display_name=:display_name,timestamp=:timestamp,text=:text,reply_to_message_id=:reply_to_message_id,media_type=:media_type,image_file_id=:image_file_id,is_bot=:is_bot"""), payload)
        except Exception:
            pass

    def recent_messages(self, chat_id: int, limit: int = 24) -> list[ChatMessage]:
        limit = max(1, min(int(limit), 100))
        with self.engine.connect() as conn:
            rows = conn.execute(text("""SELECT chat_id,message_id,user_id,display_name,timestamp,text,reply_to_message_id,media_type,image_file_id,is_bot
                FROM chat_messages WHERE chat_id=:chat_id ORDER BY timestamp DESC LIMIT :limit"""), {"chat_id": chat_id, "limit": limit}).mappings().all()
        rows.reverse(); return [ChatMessage(**dict(row)) for row in rows]

    def list_chat_ids(self) -> list[int]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT chat_id FROM chat_messages WHERE chat_id < 0 ORDER BY chat_id")).scalars().all()
        return [int(x) for x in rows]

    def add_points(self, chat_id: int, user_id: int, delta: int, win: bool = False, game: bool = True) -> dict[str, int]:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT points,wins,games_played FROM points WHERE chat_id=:c AND user_id=:u"), {"c": chat_id, "u": user_id}).mappings().first()
            p,w,g=((row["points"],row["wins"],row["games_played"]) if row else (0,0,0)); p+=delta; w+=int(win); g+=int(game)
            conn.execute(text("""INSERT INTO points(chat_id,user_id,points,wins,games_played) VALUES(:c,:u,:p,:w,:g)
                ON CONFLICT(chat_id,user_id) DO UPDATE SET points=:p,wins=:w,games_played=:g"""), {"c":chat_id,"u":user_id,"p":p,"w":w,"g":g})
            return {"points":p,"wins":w,"games_played":g}

    def save_media(self, ref) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO media_pool(chat_id,message_id,telegram_file_id,created_at,used_at,uploader_id,media_type)
                VALUES(:chat_id,:message_id,:file_id,:created_at,:used_at,:uploader_id,:media_type)
                ON CONFLICT(chat_id,telegram_file_id) DO UPDATE SET message_id=:message_id,created_at=:created_at,used_at=:used_at,uploader_id=:uploader_id,media_type=:media_type"""), {
                "chat_id":ref.chat_id,"message_id":ref.message_id,"file_id":ref.telegram_file_id,"created_at":ref.created_at,"used_at":ref.used_at,"uploader_id":ref.uploader_id,"media_type":ref.media_type})

    def list_media(self, chat_id: int, limit: int = 100) -> list[dict[str, Any]]:
        limit=max(1,min(int(limit),300))
        with self.engine.connect() as conn:
            rows=conn.execute(text("""SELECT chat_id,message_id,telegram_file_id,created_at,used_at,uploader_id,media_type
                FROM media_pool WHERE chat_id=:chat_id ORDER BY created_at DESC LIMIT :limit"""),{"chat_id":chat_id,"limit":limit}).mappings().all()
        return [dict(x) for x in rows]

    def mark_media_used(self, chat_id: int, file_id: str, used_at: float) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE media_pool SET used_at=:used WHERE chat_id=:chat_id AND telegram_file_id=:file_id"), {"used":used_at,"chat_id":chat_id,"file_id":file_id})

    def delete_media(self, chat_id: int, file_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM media_pool WHERE chat_id=:chat_id AND telegram_file_id=:file_id"), {"chat_id":chat_id,"file_id":file_id})

    def delete_used_media(self, chat_id: int) -> int:
        with self.engine.begin() as conn:
            r=conn.execute(text("DELETE FROM media_pool WHERE chat_id=:chat_id AND used_at IS NOT NULL"), {"chat_id":chat_id})
        return int(r.rowcount or 0)

    def clear_media(self, chat_id: int) -> int:
        with self.engine.begin() as conn:
            r=conn.execute(text("DELETE FROM media_pool WHERE chat_id=:chat_id"), {"chat_id":chat_id})
        return int(r.rowcount or 0)

    def media_count(self, chat_id: int, media_type: str | None = None) -> int:
        with self.engine.connect() as conn:
            if media_type:
                return int(conn.execute(text("SELECT COUNT(*) FROM media_pool WHERE chat_id=:c AND media_type=:t"), {"c":chat_id,"t":media_type}).scalar() or 0)
            return int(conn.execute(text("SELECT COUNT(*) FROM media_pool WHERE chat_id=:c"), {"c":chat_id}).scalar() or 0)

    def delete_messages(self, chat_id: int) -> int:
        with self.engine.begin() as conn:
            r=conn.execute(text("DELETE FROM chat_messages WHERE chat_id=:id"), {"id":chat_id})
        return int(r.rowcount or 0)

    def prune_stale_storage(self) -> None:
        """Remove stale data that cannot improve current replies."""
        now = time.time()
        message_cutoff = now - 14 * 86400
        media_cutoff = now - 3 * 86400
        try:
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM chat_messages WHERE timestamp < :cutoff"), {"cutoff": message_cutoff})
                conn.execute(text("DELETE FROM media_pool WHERE used_at IS NOT NULL AND used_at < :cutoff"), {"cutoff": media_cutoff})
        except Exception:
            pass
