from __future__ import annotations

import logging
import re
import types
import unicodedata

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

REQUESTS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "تصويرة", "تصويره", "photo", "photos", "pic", "pics", "image", "images", "fota"),
    "animation": ("gif", "جيڤ", "جيف", "جيف", "gifs", "انيميشن", "انميشن", "حركة", "animation"),
    "sticker": ("ستيكر", "ستكر", "ستيكرات", "sticker", "stickers", "ملصق", "ملصقات"),
    "video": ("فيديو", "فديو", "فيديوهات", "video", "videos", "vid", "clip", "clips"),
    "voice": ("فويس", "فويسات", "صوتية", "صوتيه", "رسالة صوتية", "رساله صوتيه", "voice", "voices", "voicenote"),
    "audio": ("اغنية", "أغنية", "اغنيه", "أغنيه", "موسيقى", "موسيقي", "audio", "mp3", "song", "music"),
}

# Include conjugations people actually use in chat: "ترسل", "ترسلي", "رسل", etc.
REQUEST_WORDS = (
    "ارسل", "أرسل", "ارسلي", "أرسلي", "ترسل", "ترسلي", "ترسلها", "ترسليها",
    "رسل", "رسلي", "رسلها", "رسليها", "بعت", "بعتلي", "بعث", "ابعث", "ابعثي", "ابعت", "ابعتلي",
    "هات", "هاتلي", "هاتي", "جيب", "جيبي", "وريني", "عطني", "اعطني", "أعطني",
    "send", "show", "give", "get", "share", "drop",
)


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").lower().strip()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ـ", "")
    return s


def _has_word(s: str, word: str) -> bool:
    # Arabic/Latin chat text often has attached pronouns, so allow a short
    # suffix after the request verb while still avoiding accidental matches.
    w = _normalize(word)
    if not w:
        return False
    if re.search(r"(?<!\w)" + re.escape(w) + r"(?:ها|ه|لي|ليها|هم)?(?!\w)", s):
        return True
    return False


def _requested_type(text: str) -> str | None:
    s = _normalize(text)
    if not s:
        return None
    has_request = any(_has_word(s, w) for w in REQUEST_WORDS)
    if not has_request:
        return None
    for kind, words in REQUESTS.items():
        if any(_has_word(s, w) for w in words):
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
    try:
        sender(message.chat.id, ref.telegram_file_id, reply_to_message_id=message.message_id, allow_sending_without_reply=True)
    except TypeError:
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
            text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
            kind = _requested_type(text)
            if kind:
                if _send(instance, message, kind):
                    return
                # Keep the request deterministic: don't send an unrelated AI reply.
                log.info("media requested but pool is empty: chat=%s type=%s", message.chat.id, kind)
                return
            return original(message)
        except Exception:
            log.exception("explicit media request failed")
            return original(message)

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._media_requests_installed = True
