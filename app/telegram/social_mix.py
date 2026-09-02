from __future__ import annotations

import logging
import random
import time
import types

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
    "شنو واقع هنا؟ 😭",
    "واش نتاوما ديما هكا؟ 😹",
    "أنا حاضرة، كملو 👀",
    "هادي دخلات فشي مستوى آخر 😂",
)

EXTRA_MEDIA_CHANCE = 0.07
EXTRA_MEDIA_COOLDOWN = 8 * 60


def _fallback_reply() -> str:
    return random.choice(RANDOM_REPLIES)


def _install_ai_fallback(handlers) -> None:
    """Never let an unavailable/empty AI provider turn a message into silence or 'None'."""
    ai = getattr(getattr(handlers, "rt", None), "ai", None)
    if ai is None or getattr(ai, "_social_mix_fallback_installed", False):
        return
    original = getattr(ai, "generate_text", None)
    if not callable(original):
        return

    def safe_generate(instance, prompt, system=None):
        try:
            result = original(prompt, system)
            text = str(result or "").strip()
            if not text or text.lower() in {"none", "null", "nil", "n/a"}:
                return _fallback_reply()
            return text
        except Exception:
            log.exception("AI failed; using local social fallback")
            return _fallback_reply()

    ai.generate_text = types.MethodType(safe_generate, ai)
    ai._social_mix_fallback_installed = True


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


def _send_extra_media(handlers, message) -> None:
    """Occasionally add a spontaneous media reaction after a real bot reply."""
    if not is_group(getattr(message.chat, "type", "")) or random.random() >= EXTRA_MEDIA_CHANCE:
        return
    try:
        now = time.time()
        cooldowns = getattr(handlers, "_social_extra_media_at", {})
        if now < float(cooldowns.get(message.chat.id, 0)):
            return
        ref = handlers.rt.images.choose_random_media(message.chat.id)
        if not ref:
            return
        sender = {
            "photo": handlers.bot.send_photo,
            "video": handlers.bot.send_video,
            "sticker": handlers.bot.send_sticker,
            "animation": handlers.bot.send_animation,
            "audio": handlers.bot.send_audio,
            "voice": handlers.bot.send_voice,
        }.get(ref.media_type)
        if not sender:
            return
        sender(message.chat.id, ref.telegram_file_id)
        handlers.rt.images.mark_used(ref)
        cooldowns[message.chat.id] = now + EXTRA_MEDIA_COOLDOWN
        handlers._social_extra_media_at = cooldowns
    except Exception:
        log.exception("spontaneous reply media failed")


def _install_reply_extras(handlers) -> None:
    """Hook existing reply bookkeeping without changing its reply logic."""
    original = getattr(handlers, "_remember_bot_reply", None)
    if not callable(original) or getattr(handlers, "_social_extras_installed", False):
        return

    def wrapped(instance, message, text, reply_to=None):
        result = original(message, text, reply_to)
        _send_extra_media(instance, message)
        return result

    handlers._remember_bot_reply = types.MethodType(wrapped, handlers)
    handlers._social_extras_installed = True


def install(handlers) -> None:
    """Mix AI with instant local replies and guarantee a visible fallback response."""
    original = handlers.on_message
    _install_ai_fallback(handlers)
    _install_reply_extras(handlers)

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
                reply = _fallback_reply()
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
