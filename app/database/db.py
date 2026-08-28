from __future__ import annotations
import json, time
from typing import Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SCHEMA = [
"""CREATE TABLE IF NOT EXISTS chat_settings (
 chat_id BIGINT PRIMARY KEY, settings_json TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS points (
 chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL, points INTEGER NOT NULL DEFAULT 0,
 wins INTEGER NOT NULL DEFAULT 0, games_played INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY (chat_id,user_id))""",
"""CREATE TABLE IF NOT EXISTS chat_state (
 chat_id BIGINT PRIMARY KEY, state_json TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
]


def normalize_database_url(url: str) -> str:
    if not url:
        return "sqlite:////tmp/kyoos.sqlite3" if "/tmp" in "/tmp" else "sqlite:///kyoos.sqlite3"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Database:
    def __init__(self, url: str):
        self.url = normalize_database_url(url)
        self.engine: Engine = create_engine(self.url, pool_pre_ping=True, future=True)
        self.init()

    def init(self) -> None:
        with self.engine.begin() as conn:
            for stmt in SCHEMA:
                conn.execute(text(stmt))

    def get_json(self, table: str, key_col: str, key: int, default: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(text(f"SELECT * FROM {table} WHERE {key_col}=:key"), {"key": key}).mappings().first()
        if not row:
            return default or {}
        raw = row.get("settings_json") or row.get("state_json") or "{}"
        try:
            return json.loads(raw)
        except Exception:
            return default or {}

    def save_chat_settings(self, chat_id: int, payload: dict[str, Any]) -> None:
        now, raw = time.time(), json.dumps(payload, ensure_ascii=False)
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO chat_settings(chat_id,settings_json,updated_at) VALUES (:id,:raw,:ts)
            ON CONFLICT(chat_id) DO UPDATE SET settings_json=:raw,updated_at=:ts"""), {"id": chat_id, "raw": raw, "ts": now})

    def save_state(self, chat_id: int, payload: dict[str, Any]) -> None:
        now, raw = time.time(), json.dumps(payload, ensure_ascii=False)
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO chat_state(chat_id,state_json,updated_at) VALUES (:id,:raw,:ts)
            ON CONFLICT(chat_id) DO UPDATE SET state_json=:raw,updated_at=:ts"""), {"id": chat_id, "raw": raw, "ts": now})

    def add_points(self, chat_id: int, user_id: int, delta: int, win: bool = False, game: bool = True) -> dict[str, int]:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT points,wins,games_played FROM points WHERE chat_id=:c AND user_id=:u"), {"c": chat_id, "u": user_id}).mappings().first()
            p, w, g = ((row["points"], row["wins"], row["games_played"]) if row else (0, 0, 0))
            p += delta; w += int(win); g += int(game)
            conn.execute(text("""INSERT INTO points(chat_id,user_id,points,wins,games_played) VALUES (:c,:u,:p,:w,:g)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET points=:p,wins=:w,games_played=:g"""), {"c":chat_id,"u":user_id,"p":p,"w":w,"g":g})
            return {"points":p,"wins":w,"games_played":g}
