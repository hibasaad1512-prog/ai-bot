from __future__ import annotations

import logging
import random
import threading
import time
import types

from app.config import settings
from app.models import ChatMessage
from app.ai.privacy import PrivacyFilter
from app.memory.store import MemoryStore
from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

# Local replies are a spice, not the main personality. The AI should handle most messages.
RANDOM_REPLIES = (
    "ههههه 😭",
    "واش بصح؟",
    "آه لا لا 😂",
    "شنو هادشي 😭",
    "مزيان هادي",
    "أنا غير كنشوف 👀",
    "هادشي خرج شوية على السيطرة 😹",
    "hmm 👀",
    "واخاا",
    "شنو واقع هنا؟",
    "كملو كملو 😂",
    "أنا حاضرة 😼",
    "nah 😭",
    "bro 💀",
)

# Keep media spontaneous but uncommon enough to feel intentional.
EXTRA_MEDIA_CHANCE = 0.16
EXTRA_MEDIA_COOLDOWN = 4 * 60

# Background analysis is deliberately throttled so it never becomes the reason a reply is slow.
ANALYSIS_EVERY = 6
ANALYSIS_COOLDOWN = 90


def _fallback_reply() -> str:
    return random.choice(RANDOM_REPLIES)


def _install_ai_fallback(handlers) -> None:
    """Never let an unavailable/empty AI provider turn a message into silence."""
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
        log.exception("could not remember local-branch user message")


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
        log.exception("local-branch moderation check failed")
    return True


def _background_analyze(handlers, message, user_text: str, bot_reply: str) -> None:
    """Analyze useful stable context after the reply, never on the request path."""
    try:
        ai = handlers.rt.ai
        now = time.time()
        state = getattr(handlers, "_merva_analysis_state", {})
        count = int(state.get(message.chat.id, {}).get("count", 0)) + 1
        last = float(state.get(message.chat.id, {}).get("last", 0))
        state[message.chat.id] = {"count": count, "last": last}
        handlers._merva_analysis_state = state
        if count % ANALYSIS_EVERY != 0 or now - last < ANALYSIS_COOLDOWN:
            return
        state[message.chat.id]["last"] = now

        def worker() -> None:
            try:
                prompt = (
                    "Extract only stable, useful facts explicitly stated in this short group exchange. "
                    "Do not store jokes, insults, secrets, credentials, personal contact data, or one-off claims. "
                    "Return JSON only: {\"memories\":[{\"key\":\"short_key\",\"value\":\"short fact\"}]} .\n\n"
                    f"USER: {user_text[:700]}\nMERVA: {bot_reply[:500]}"
                )
                result = ai.generate_structured(
                    prompt,
                    {"type": "object", "properties": {"memories": {"type": "array"}}},
                    system="You are Merva's background memory analyst. Be conservative; empty memories is a valid result.",
                )
                if not isinstance(result, dict):
                    return
                memories = result.get("memories") or []
                store = MemoryStore(handlers.rt.db)
                for item in memories[:2]:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "").strip()[:100]
                    value = str(item.get("value") or "").strip()
                    if key and value and len(value) <= 500:
                        store.remember(message.chat.id, message.from_user.id, value, memory_key="auto:" + key, memory_type="ai")
                log.debug("Merva background analysis complete chat=%s memories=%s", message.chat.id, len(memories))
            except Exception:
                log.debug("Merva background analysis skipped", exc_info=True)

        threading.Thread(target=worker, name="merva-memory-analysis", daemon=True).start()
    except Exception:
        log.debug("could not schedule background analysis", exc_info=True)


def _send_extra_media(handlers, message) -> None:
    """Occasionally add context-independent media from the group's collected pool."""
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
        log.debug("spontaneous reply media failed", exc_info=True)


def _install_reply_extras(handlers) -> None:
    original = getattr(handlers, "_remember_bot_reply", None)
    if not callable(original) or getattr(handlers, "_social_extras_installed", False):
        return

    def wrapped(instance, message, text, reply_to=None):
        result = original(message, text, reply_to)
        _send_extra_media(instance, message)
        try:
            user_text = (getattr(message, "text", None) or "").strip()
            if user_text and text:
                _background_analyze(instance, message, user_text, str(text))
        except Exception:
            pass
        return result

    handlers._remember_bot_reply = types.MethodType(wrapped, handlers)
    handlers._social_extras_installed = True


def install(handlers) -> None:
    """Use AI as the main voice, local reactions as occasional social spice, and analyze in background."""
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
                and random.random() < 0.12
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
                    log.exception("could not remember local social reply")
                return
        except Exception:
            log.exception("local social mix failed; falling back to AI")
        return original(message)

    handlers.on_message = wrapped
