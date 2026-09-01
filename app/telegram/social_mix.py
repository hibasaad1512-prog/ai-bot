from __future__ import annotations

import logging
import random
import time

from app.config import settings
from app.models import ChatMessage
from app.ai.privacy import PrivacyFilter
from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

RANDOM_REPLIES = (
    "ههههه شنو هاد 😂",
    "واش بصح؟ 😭",
    "الميرفاوية كتراقب بصمت 👀",
    "آه لا لا 😹",
    "شنو كتخربقو تما؟",
    "مزيان هادي 😂",
    "أنا ما شفت والو… 👀",
    "mrrp 😼",
    "واخااا 😭",
    "هادشي خرج على السيطرة شوية 😹",
    "hmm… interesting 👀",
    "meow.",
)


def _remember_user(handlers, message, safe_text: str) -> None:
    try:
        handlers.rt.memory.add(
            ChatMessage(
                chat_id=message.chat.id,
                message_id=message.message_id,
                user_id=message.from_user.id,
                display_name=(message.from_user.first_name or message.from_user.username or "user"),
                timestamp=message.date or time.time(),
                text=safe_text,
                reply_to_message_id=(message.reply_to_message.message_id if message.reply_to_message else None),
                is_bot=False,
            )
        )
    except Exception:
        log.exception("could not remember random-branch user message")


def _moderation_allows(handlers, message, text: str) -> bool:
    if not settings.enabled_moderation or not text:
        return True
    try:
        recent = [x.text for x in handlers.rt.memory.recent(message.chat.id, 12) if x.text]
        mod = handlers.rt.moderation.detect(text, recent)
        if mod and mod.action == "delete":
            try:
                handlers.bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
            return False
    except Exception:
        log.exception("random-branch moderation check failed")
    return True


def install(handlers) -> None:
    """Mix instant local replies with the existing AI path without disabling memory/moderation."""
    original = handlers.on_message

    def wrapped(message):
        try:
            text = (getattr(message, "text", None) or "").strip()
            if (
                getattr(message, "from_user", None)
                and is_group(getattr(message.chat, "type", ""))
                and not getattr(message.from_user, "is_bot", False)
                and text
                and not text.startswith("/")
                and random.random() < 0.30
            ):
                privacy = PrivacyFilter.sanitize(text)
                if privacy.sensitive or privacy.redacted:
                    return original(message)
                if not _moderation_allows(handlers, message, text):
                    return
                _remember_user(handlers, message, privacy.text)
                reply = random.choice(RANDOM_REPLIES)
                handlers.bot.send_message(
                    message.chat.id,
                    reply,
                    reply_to_message_id=message.message_id,
                    allow_sending_without_reply=True,
                )
                try:
                    handlers._remember_bot_reply(message, reply, message.message_id)
                except Exception:
                    log.exception("could not remember local random reply")
                return
        except Exception:
            log.exception("local social mix failed; falling back to AI")
        return original(message)

    handlers.on_message = wrapped
