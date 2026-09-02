from __future__ import annotations

import difflib
import logging
import re
import types
import unicodedata

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

REQUESTS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "تصويرة", "تصويره", "photo", "photos", "pic", "pics", "image", "images", "fota"),
    "animation": ("gif", "جيڤ", "جيف", "gifs", "انيميشن", "انميشن", "حركة", "animation"),
    "sticker": ("ستيكر", "ستكر", "ستيكرات", "sticker", "stickers", "ملصق", "ملصقات"),
    "video": ("فيديو", "فديو", "فيديوهات", "video", "videos", "vid", "clip", "clips"),
    "voice": ("فويس", "فويسات", "صوتية", "صوتيه", "رسالة صوتية", "رساله صوتيه", "voice", "voices", "voicenote"),
    "audio": ("اغنية", "أغنية", "اغنيه", "أغنيه", "موسيقى", "موسيقي", "audio", "mp3", "song", "music"),
}

REQUEST_WORDS = (
    "ارسل", "أرسل", "ارسلي", "أرسلي", "ترسل", "ترسلي", "ترسلها", "ترسليها", "ارسله", "ارسلها", "ارسللي", "ارسليلي",
    "رسل", "رسلي", "رسلها", "رسليها", "بعت", "بعتلي", "بعتليها", "بعث", "ابعث", "ابعثي", "ابعت", "ابعتلي", "ابعتليها",
    "هات", "هاتلي", "هاتي", "جيب", "جيبي", "وريني", "عطني", "اعطني", "أعطني", "send", "show", "give", "get", "share", "drop",
)

REPLAY_WORDS = (
    "كرر", "كرري", "كرره", "كررها", "عاود", "عاودي", "عاودها", "رجع", "رجعي", "رجعها", "أعد", "اعد", "أعيد", "اعيد",
    "ارسلها", "ارسله", "رسلها", "ترسلها", "بعتليها", "ابعتليها", "replay", "repeat", "resend", "again",
)

MEDIA_TYPES = ("photo", "video", "sticker", "animation", "audio", "voice")


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").lower().strip()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("ـ", "")


def _has_word(s: str, word: str) -> bool:
    w = _normalize(word)
    return bool(w and re.search(r"(?<!\w)" + re.escape(w) + r"(?:ها|ه|لي|ليها|ليلي|هم)?(?!\w)", s))


def _requested_type(text: str) -> str | None:
    s = _normalize(text)
    if not s or not any(_has_word(s, w) for w in REQUEST_WORDS):
        return None
    for kind, words in REQUESTS.items():
        if any(_has_word(s, w) for w in words):
            return kind
    return None


def _is_replay_request(text: str) -> bool:
    s = _normalize(text)
    return bool(s and any(_has_word(s, w) for w in REPLAY_WORDS))


def _file_from_media(message, media_type: str):
    obj = getattr(message, media_type, None)
    if media_type == "photo" and obj:
        return obj[-1].file_id
    return getattr(obj, "file_id", None) if obj else None


def _sender(handler, media_type: str):
    return {
        "photo": handler.bot.send_photo,
        "animation": handler.bot.send_animation,
        "sticker": handler.bot.send_sticker,
        "video": handler.bot.send_video,
        "voice": handler.bot.send_voice,
        "audio": handler.bot.send_audio,
    }.get(media_type)


def _send_file(handler, message, media_type: str, file_id: str) -> bool:
    sender = _sender(handler, media_type)
    if not sender or not file_id:
        return False
    try:
        try:
            sender(message.chat.id, file_id, reply_to_message_id=message.message_id, allow_sending_without_reply=True)
        except TypeError:
            sender(message.chat.id, file_id, reply_to_message_id=message.message_id)
        return True
    except Exception:
        log.warning("media send failed chat=%s type=%s", getattr(message.chat, "id", None), media_type, exc_info=True)
        return False


def _memory_media(handler, message, media_type: str | None = None):
    """Find media already learned from this group, including persisted history."""
    try:
        recent = handler.rt.memory.recent(message.chat.id, 80)
    except Exception:
        return None
    for item in reversed(recent):
        if not getattr(item, "image_file_id", None):
            continue
        if media_type and getattr(item, "media_type", None) != media_type:
            continue
        if getattr(item, "is_bot", False):
            continue
        return item
    return None


def _send_from_memory(handler, message, media_type: str | None = None, message_id: int | None = None) -> bool:
    try:
        recent = handler.rt.memory.recent(message.chat.id, 120)
    except Exception:
        return False
    for item in reversed(recent):
        if getattr(item, "is_bot", False) or not getattr(item, "image_file_id", None):
            continue
        if message_id is not None and int(getattr(item, "message_id", -1)) != int(message_id):
            continue
        kind = getattr(item, "media_type", None)
        if kind not in MEDIA_TYPES or (media_type and kind != media_type):
            continue
        if _send_file(handler, message, kind, item.image_file_id):
            return True
    return False


def _send(handler, message, media_type: str) -> bool:
    # Memory is checked first: it contains the exact file_id learned from the
    # actual Telegram message, and also survives a pool cache miss.
    ref = _memory_media(handler, message, media_type)
    if ref and _send_file(handler, message, media_type, ref.image_file_id):
        return True

    # Try several pool candidates instead of giving up on the first stale file_id.
    tried: set[str] = set()
    for _ in range(4):
        ref = handler.rt.images.choose(message.chat.id, media_type=media_type, avoid_file_ids=tried)
        if not ref:
            break
        tried.add(ref.telegram_file_id)
        if _send_file(handler, message, media_type, ref.telegram_file_id):
            handler.rt.images.mark_used(ref)
            return True
    return False


def _reply_media_kind(reply) -> str | None:
    for kind in MEDIA_TYPES:
        if _file_from_media(reply, kind):
            return kind
    return None


def _send_replied(handler, message, media_type: str | None = None) -> bool:
    reply = getattr(message, "reply_to_message", None)
    if not reply:
        return False
    kind = media_type or _reply_media_kind(reply)
    if kind and _send_file(handler, message, kind, _file_from_media(reply, kind)):
        return True
    # Telegram may give us only the reply's message_id in some restricted cases;
    # fall back to our already-stored ChatMessage/file_id.
    rid = getattr(reply, "message_id", None)
    return bool(rid is not None and _send_from_memory(handler, message, media_type, rid))


def _send_replied_text(handler, message) -> bool:
    reply = getattr(message, "reply_to_message", None)
    if not reply:
        return False
    text = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
    if not text.strip():
        return False
    try:
        handler.bot.send_message(message.chat.id, text, reply_to_message_id=message.message_id, allow_sending_without_reply=True)
    except TypeError:
        handler.bot.send_message(message.chat.id, text, reply_to_message_id=message.message_id)
    except Exception:
        return False
    return True


def _replay_reply(handler, message) -> bool:
    if _send_replied(handler, message):
        return True
    return _send_replied_text(handler, message)


def _target_from_prompt(prompt: str) -> str:
    m = re.search(r"CURRENT USER MESSAGE — ABSOLUTE HIGHEST PRIORITY:\s*\n(.*?)\n\nCONTEXT:", str(prompt), re.S)
    return m.group(1).strip() if m else ""


def _strip_emoji_spam(text: str) -> str:
    # Keep at most one emoji. This is deterministic and prevents the model from
    # turning every answer into an emoji-heavy/cringe reply.
    if not text:
        return text
    emoji_re = re.compile(r"[\U0001F1E6-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")
    seen = 0
    out = []
    for ch in text:
        if emoji_re.match(ch):
            if seen:
                continue
            seen += 1
        out.append(ch)
    return "".join(out).strip()


def _reply_is_duplicate(handler, chat_id: int, reply: str) -> bool:
    norm = re.sub(r"\s+", " ", _normalize(reply)).strip()
    if len(norm) < 8:
        return False
    try:
        recent = handler.rt.memory.recent(chat_id, 12)
    except Exception:
        return False
    for item in reversed(recent):
        if not getattr(item, "is_bot", False) or not getattr(item, "text", None):
            continue
        old = re.sub(r"\s+", " ", _normalize(item.text)).strip()
        if norm == old or difflib.SequenceMatcher(None, norm, old).ratio() >= 0.88:
            return True
    return False


def _patch_ai(handlers) -> None:
    ai = getattr(handlers.rt, "ai", None)
    if not ai or getattr(ai, "_strict_social_guard", False):
        return
    original = getattr(ai, "generate_text", None)
    if not callable(original):
        return

    def safe_generate(instance, prompt, system=None):
        target = _target_from_prompt(prompt)
        try:
            result = str(original(prompt, system) or "").strip()
            if not result or result.lower() in {"none", "null", "nil", "n/a"} or _wrong_script(target, result):
                return "מفهمتش، عاودها ليا" if re.search(r"[\u0600-\u06ff]", target) else "I didn't catch that"

            result = _strip_emoji_spam(result)
            if _reply_is_duplicate(instance, getattr(getattr(instance, "_last_ai_message", None), "chat_id", 0), result):
                retry_system = (system or "") + "\nCRITICAL: Your previous candidate repeated a recent bot reply. Write a genuinely different short reply; do not reuse its wording or punchline."
                fresh = str(original(prompt, retry_system) or "").strip()
                fresh = _strip_emoji_spam(fresh)
                if fresh and not _wrong_script(target, fresh) and not _reply_is_duplicate(instance, getattr(getattr(instance, "_last_ai_message", None), "chat_id", 0), fresh):
                    result = fresh
            return result
        except Exception:
            return "مفهمتش، عاودها ليا" if re.search(r"[\u0600-\u06ff]", target) else "I didn't catch that"

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

    # The AI wrapper needs the current chat id for local duplicate detection.
    # Store it on the handler immediately before generation is reached.
    old_on_message = original

    def wrapped(instance, message):
        try:
            if not is_group(getattr(message.chat, "type", "")):
                return old_on_message(message)
            text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
            state = {}
            try:
                state = instance.rt.db.get_json("chat_state", "chat_id", int(message.chat.id), {})
            except Exception:
                pass
            if state.get("media_requests_enabled", True) is False:
                return old_on_message(message)

            # Exact reply/replay has absolute priority over AI.
            if getattr(message, "reply_to_message", None) and (_is_replay_request(text) or _requested_type(text)):
                if _send_replied(instance, message, _requested_type(text)):
                    return
                if _is_replay_request(text) and _replay_reply(instance, message):
                    return

            kind = _requested_type(text)
            if kind:
                if _send(instance, message, kind):
                    return
                # An explicit media request must never fall through to unrelated AI.
                log.info("media requested but unavailable: chat=%s type=%s", message.chat.id, kind)
                return

            # Remember the current chat so the duplicate guard can compare against
            # the right group's recent bot replies without another AI call.
            try:
                instance._last_ai_message = message
            except Exception:
                pass
            return old_on_message(message)
        except Exception:
            log.exception("explicit media/replay request failed")
            return old_on_message(message)

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._media_requests_installed = True
