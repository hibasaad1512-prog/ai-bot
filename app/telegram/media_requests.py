from __future__ import annotations

import logging
import re
import types

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

REQUESTS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "photo", "photos", "pic", "pics", "image", "images"),
    "animation": ("gif", "جيڤ", "جيف", "gifs", "انيميشن", "animation"),
    "sticker": ("ستيكر", "ستكر", "ستيكرات", "sticker", "stickers", "ملصق"),
    "video": ("فيديو", "فديو", "فيديوهات", "video", "videos", "vid"),
    "voice": ("فويس", "فويسات", "صوتية", "voice", "voices", "voicenote", "رسالة صوتية"),
    "audio": ("اغنية", "أغنية", "موسيقى", "audio", "mp3", "song"),
}

REQUEST_WORDS = (
    "ارسل", "أرسل", "ارسلي", "أرسلي", "بعت", "ابعث", "ابعت", "بعث",
    "send", "show", "give", "هات", "هاتلي", "جيب", "وريني", "عطني", "اعطني", "أعطني",
)


def _requested_type(text: str) -> str | None:
    s = (text or "").strip().lower()
    if not s or not any(w in s for w in REQUEST_WORDS):
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
    }.get(media_type)
    if not sender:
        return False
    # Telegram gets the file_id directly: no command, no text dump, no fake URL.
    sender(message.chat.id, ref.telegram_file_id, reply_to_message_id=message.message_id)
    handler.rt.images.mark_used(ref)
    return True


def _target_from_prompt(prompt: str) -> str:
    m = re.search(r"CURRENT USER MESSAGE — ABSOLUTE HIGHEST PRIORITY:\s*\n(.*?)\n\nCONTEXT:", str(prompt), re.S)
    return m.group(1).strip() if m else ""


def _wrong_script(target: str, reply: str) -> bool:
    if not target or not reply:
        return False
    if re.search(r"[\u0600-\u06ff]", target):
        return bool(re.search(r"[\u0400-\u04ff\u0370-\u03ff\u0590-\u05ff\u0900-\u097f\u3040-\u30ff\u4e00-\u9fff]", reply))
    if re.search(r"[A-Za-z]", target):
        return bool(re.search(r"[\u0400-\u04ff\u0370-\u03ff\u0590-\u05ff\u0900-\u097f\u3040-\u30ff\u4e00-\u9fff]", reply))
    return False


def _patch_ai(handlers) -> None:
    ai = getattr(handlers.rt, "ai", None)
    if not ai or getattr(ai, "_strict_social_guard", False):
        return
    original = getattr(ai, "generate_text", None)
    if not callable(original):
        return

    def safe_generate(instance, prompt, system=None):
        try:
            result = str(original(prompt, system) or "").strip()
            target = _target_from_prompt(prompt)
            if not result or result.lower() in {"none", "null", "nil", "n/a"} or _wrong_script(target, result):
                # Do not replace an AI failure with an unrelated word/phrase.
                if re.search(r"[\u0600-\u06ff]", target):
                    return "مفهمتش، عاودها ليا 😭"
                return "I didn't catch that 😭"
            return result
        except Exception:
            if re.search(r"[\u0600-\u06ff]", _target_from_prompt(prompt)):
                return "مفهمتش، عاودها ليا 😭"
            return "I didn't catch that 😭"

    ai.generate_text = types.MethodType(safe_generate, ai)
    ai._strict_social_guard = True


def _patch_context(handlers) -> None:
    # The old handler added random callbacks/remixes from unrelated messages.
    # Keep normal recent conversation context, but force DIRECT_REPLY mode.
    if getattr(handlers, "_strict_context_guard", False):
        return
    original = getattr(handlers, "_conversation_context", None)
    if not callable(original):
        return

    def build(instance, message, current_text):
        return original(message, current_text), "DIRECT_REPLY"

    handlers._build_ai_context = types.MethodType(build, handlers)
    handlers._strict_context_guard = True


def install(handlers) -> None:
    if getattr(handlers, "_media_requests_installed", False):
        return
    original = handlers.on_message
    if not callable(original):
        return

    _patch_ai(handlers)
    _patch_context(handlers)

    def wrapped(instance, message):
        try:
            if not is_group(getattr(message.chat, "type", "")):
                return original(message)
            kind = _requested_type(getattr(message, "text", None) or getattr(message, "caption", None) or "")
            if kind:
                if _send(instance, message, kind):
                    return
                # No matching media in this group: don't send a fake command or file id.
                return
            return original(message)
        except Exception:
            log.exception("explicit media request failed")
            return original(message)

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._media_requests_installed = True
