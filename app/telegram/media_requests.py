from __future__ import annotations

import logging
import re
import types

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

# Explicit media requests are handled before AI. Supports common Arabic/Darija,
# English and French forms so the request never gets turned into a random AI reply.
REQUESTS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "تصويرة", "تصويرة", "photo", "photos", "pic", "pics", "image", "images", "photo"),
    "animation": ("gif", "gifs", "جيڤ", "جيف", "جييف", "انيميشن", "animation", "gif"),
    "sticker": ("ستيكر", "ستكر", "ستيكرات", "sticker", "stickers", "ملصق", "ملصقات"),
    "video": ("فيديو", "فديو", "فيديوهات", "video", "videos", "vid", "vidéo", "videos"),
    "voice": ("فويس", "فويسات", "صوتية", "صوتيه", "رسالة صوتية", "voice", "voices", "voicenote", "voice note", "vocal"),
    "audio": ("اغنية", "أغنية", "اغاني", "أغاني", "موسيقى", "audio", "mp3", "song", "musique", "chanson"),
}

REQUEST_WORDS = (
    "ارسل", "أرسل", "ارسلي", "أرسلي", "ارسللي", "أرسللي", "رسل", "رسلي", "بعث", "بعثلي", "بعت", "بعتلي",
    "ابعث", "ابعثلي", "ابعت", "ابعتلي", "هات", "هاتلي", "جيب", "جيبلي", "وريني", "عطني", "اعطني", "أعطني",
    "send", "send me", "show", "show me", "give", "give me", "envoie", "envoie-moi", "envoyer", "donne", "montre",
)


def _requested_type(text: str) -> str | None:
    s = (text or "").strip().lower()
    if not s:
        return None
    # A request verb is required for normal words. Also accept very explicit
    # one-word commands such as "gif" or "sticker" followed by nothing.
    explicit_only = {"gif", "gifs", "photo", "pic", "image", "sticker", "stickers", "video", "vid", "voice", "vocal", "صورة", "فيديو", "فويس", "ستيكر"}
    has_verb = any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", s) for w in REQUEST_WORDS)
    if not has_verb and s not in explicit_only:
        return None
    for kind, words in REQUESTS.items():
        if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", s) for w in words):
            return kind
    return None


def _send(handler, message, media_type: str) -> bool:
    # The setting is per-group. Default is ON.
    try:
        state = handler.rt.db.get_json("chat_state", "chat_id", int(message.chat.id), {})
        if state.get("media_requests_enabled", True) is False:
            return False
    except Exception:
        pass
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
        # No random old-message callback/remix. Only the actual conversation context.
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
                # If media exists, ALWAYS send it directly. Never let AI answer an explicit request.
                if _send(instance, message, kind):
                    return
                # No matching item in this group's pool: stay silent rather than inventing a reply.
                return
            return original(message)
        except Exception:
            log.exception("explicit media request failed")
            return original(message)

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._media_requests_installed = True
