from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

from app.models import ChatMessage


MAX_MESSAGES_PER_CHAT = 500
MAX_MEDIA_PER_CHAT = 200


def _user_name(user) -> str:
    return (getattr(user, "first_name", None) or getattr(user, "username", None) or "user")[:200]


def _media(m) -> tuple[str | None, str | None]:
    if getattr(m, "photo", None):
        return "photo", m.photo[-1].file_id
    if getattr(m, "video", None):
        return "video", m.video.file_id
    if getattr(m, "sticker", None):
        return "sticker", m.sticker.file_id
    if getattr(m, "animation", None):
        return "animation", m.animation.file_id
    if getattr(m, "document", None):
        return "document", m.document.file_id
    if getattr(m, "audio", None):
        return "audio", m.audio.file_id
    if getattr(m, "voice", None):
        return "voice", m.voice.file_id
    if getattr(m, "video_note", None):
        return "video_note", m.video_note.file_id
    return None, None


def _install_schema(db) -> None:
    with db.engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS telegram_users (
            user_id BIGINT PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            is_bot BOOLEAN NOT NULL DEFAULT FALSE,
            last_seen DOUBLE PRECISION NOT NULL
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS telegram_chats (
            chat_id BIGINT PRIMARY KEY,
            chat_type TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            last_seen DOUBLE PRECISION NOT NULL
        )"""))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_seen ON telegram_users(last_seen DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chats_seen ON telegram_chats(last_seen DESC)"))


def _save_metadata(db, m) -> None:
    user = getattr(m, "from_user", None)
    chat = getattr(m, "chat", None)
    now = float(getattr(m, "date", None) or time.time())
    with db.engine.begin() as conn:
        if user:
            conn.execute(text("""INSERT INTO telegram_users(user_id,username,first_name,last_name,is_bot,last_seen)
                VALUES(:id,:username,:first,:last,:bot,:seen)
                ON CONFLICT(user_id) DO UPDATE SET username=:username,first_name=:first,last_name=:last,is_bot=:bot,last_seen=:seen"""), {
                "id": int(user.id), "username": getattr(user, "username", "") or "",
                "first": getattr(user, "first_name", "") or "", "last": getattr(user, "last_name", "") or "",
                "bot": bool(getattr(user, "is_bot", False)), "seen": now})
        if chat:
            conn.execute(text("""INSERT INTO telegram_chats(chat_id,chat_type,title,username,last_seen)
                VALUES(:id,:type,:title,:username,:seen)
                ON CONFLICT(chat_id) DO UPDATE SET chat_type=:type,title=:title,username=:username,last_seen=:seen"""), {
                "id": int(chat.id), "type": getattr(chat, "type", "") or "",
                "title": getattr(chat, "title", "") or "", "username": getattr(chat, "username", "") or "", "seen": now})


def _save_message(db, m) -> None:
    user = getattr(m, "from_user", None)
    if not user:
        return
    media_type, file_id = _media(m)
    text_value = (getattr(m, "text", None) or getattr(m, "caption", None) or "")[:4000]
    cm = ChatMessage(
        chat_id=int(m.chat.id), message_id=int(m.message_id), user_id=int(user.id),
        display_name=_user_name(user), timestamp=float(getattr(m, "date", None) or time.time()),
        text=text_value, reply_to_message_id=(getattr(getattr(m, "reply_to_message", None), "message_id", None)),
        media_type=media_type, image_file_id=file_id, is_bot=bool(getattr(user, "is_bot", False)),
    )
    db.save_message(cm)
    if file_id:
        with db.engine.begin() as conn:
            conn.execute(text("""INSERT INTO media_pool(chat_id,message_id,telegram_file_id,created_at,used_at,uploader_id,media_type)
                VALUES(:chat,:msg,:file,:created,:used,:user,:type)
                ON CONFLICT(chat_id,telegram_file_id) DO UPDATE SET message_id=:msg,created_at=:created,uploader_id=:user,media_type=:type"""), {
                "chat": int(m.chat.id), "msg": int(m.message_id), "file": file_id,
                "created": float(getattr(m, "date", None) or time.time()), "used": None,
                "user": int(user.id), "type": media_type or "unknown"})
    with db.engine.begin() as conn:
        conn.execute(text("""DELETE FROM chat_messages WHERE chat_id=:chat AND message_id NOT IN
            (SELECT message_id FROM chat_messages WHERE chat_id=:chat ORDER BY timestamp DESC LIMIT :limit)"""),
            {"chat": int(m.chat.id), "limit": MAX_MESSAGES_PER_CHAT})
        conn.execute(text("""DELETE FROM media_pool WHERE chat_id=:chat AND telegram_file_id NOT IN
            (SELECT telegram_file_id FROM media_pool WHERE chat_id=:chat ORDER BY created_at DESC LIMIT :limit)"""),
            {"chat": int(m.chat.id), "limit": MAX_MEDIA_PER_CHAT})


def register_smart_archive(bot, runtime) -> None:
    try:
        _install_schema(runtime.db)
    except Exception:
        # Archive must never prevent the bot from starting.
        return

    @bot.message_handler(content_types=["animation", "document", "audio", "voice", "video_note"])
    def archive_extra_media(message):
        try:
            _save_metadata(runtime.db, message)
            _save_message(runtime.db, message)
        except Exception:
            return
