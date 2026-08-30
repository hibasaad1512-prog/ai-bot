"""Lightweight Telegram archive helpers.

Only metadata and Telegram file IDs are retained; binary media is temporary.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
logger = logging.getLogger(__name__)

def _now():
    return datetime.now(timezone.utc)

def _media_info(message: Any):
    for attr, kind in (("photo","photo"),("video","video"),("animation","animation"),("document","document"),("audio","audio"),("voice","voice"),("video_note","video_note"),("sticker","sticker")):
        value = getattr(message, attr, None)
        if value:
            obj = value[-1] if isinstance(value, (list, tuple)) else value
            return getattr(obj, "file_id", None), kind, getattr(obj, "file_size", None)
    return None, None, None

def _get_store(runtime):
    for name in ("db", "database", "storage"):
        store = getattr(runtime, name, None)
        if store is not None:
            return store
    return None

def register_smart_archive(bot=None, runtime=None):
    """Install non-blocking archive helpers; compatible with KyoosBot startup."""
    if runtime is None:
        runtime = bot
    if runtime is None:
        return
    runtime.smart_archive_enabled = True
    runtime.smart_archive_media_policy = "telegram_file_id_only"

    async def archive_message(message):
        try:
            store = _get_store(runtime)
            if store is None:
                return
            chat = getattr(message, "chat", None)
            user = getattr(message, "from_user", None)
            file_id, media_type, file_size = _media_info(message)
            payload = {
                "chat_id": getattr(chat, "id", None),
                "chat_title": getattr(chat, "title", None),
                "user_id": getattr(user, "id", None),
                "message_id": getattr(message, "message_id", None),
                "text": getattr(message, "text", None) or getattr(message, "caption", None),
                "media_type": media_type,
                "file_id": file_id,
                "file_size": file_size,
                "created_at": _now(),
            }
            fn = getattr(store, "archive_message", None)
            if callable(fn):
                result = fn(payload)
                if hasattr(result, "__await__"):
                    await result
        except Exception:
            logger.exception("smart archive failed; continuing without blocking bot")

    runtime.archive_message = archive_message
    logger.info("Smart archive enabled (metadata/file_id only)")
