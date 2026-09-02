from __future__ import annotations

import logging
import re
import types

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

# Explicit media requests should bypass the AI reply path and immediately send
# one random matching item already collected from this group.
REQUESTS = {
    "photo": ("صورة", "صور", "pic", "picture", "photo", "image", "img"),
    "animation": ("gif", "جيڤ", "جيف", "gif", "انيميشن", "حركة"),
    "sticker": ("ستيكر", "ستكر", "sticker", "ملصق"),
    "video": ("فيديو", "فديو", "video", "vid"),
    "voice": ("فويس", "صوتية", "صوت", "voice", "voicenote", "رسالة صوتية"),
    "audio": ("اغنية", "أغنية", "موسيقى", "audio", "mp3", "song"),
}


def _requested_type(text: str) -> str | None:
    s = (text or "").strip().lower()
    if not s:
        return None
    # Require an explicit request verb/word so ordinary conversation is untouched.
    request_words = ("ارسل", "أرسل", "ارسلي", "أرسلي", "هات", "هاتلي", "جيب", "وريني", "send", "show", "give", "بعث", "بعت")
    if not any(w in s for w in request_words):
        return None
    for kind, words in REQUESTS.items():
        if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", s) for w in words):
            return kind
    return None


def _send(handler, message, media_type: str) -> bool:
    ref = handler.rt.images.choose(message.chat.id, media_type=media_type)
    if not ref:
        return False
    sender = {
        "photo": handler.bot.send_photo,
        "animation": handler.bot.send_animation,
        "sticker": handler.bot.send_sticker,
        "video": handler.bot.send_video,
        "voice": handler.bot.send_voice,
        "audio": handler.bot.send_audio,
    }[media_type]
    sender(message.chat.id, ref.telegram_file_id, reply_to_message_id=message.message_id)
    handler.rt.images.mark_used(ref)
    return True


def install(handlers) -> None:
    if getattr(handlers, "_media_requests_installed", False):
        return
    original = handlers.on_message
    if not callable(original):
        return

    def wrapped(instance, message):
        try:
            if not is_group(getattr(message.chat, "type", "")):
                return original(message)
            kind = _requested_type(getattr(message, "text", None) or getattr(message, "caption", None) or "")
            if not kind:
                return original(message)
            if _send(instance, message, kind):
                return
            # Don't invent a fake media response when the group has no matching media.
            return original(message)
        except Exception:
            log.exception("explicit media request failed; falling back to normal reply")
            return original(message)

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._media_requests_installed = True
