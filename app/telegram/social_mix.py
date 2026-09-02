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

# AI is the voice. Local text is used only if every configured provider fails.
RANDOM_REPLIES = ("هههه 😭", "واش بصح؟", "آه لا 😭", "شنو هادشي؟", "مزيان هادي", "👀")
ANALYSIS_EVERY = 6
ANALYSIS_COOLDOWN = 90

MEDIA_WORDS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "صويرة", "photo", "photos", "pic", "pics"),
    "video": ("فيديو", "فيديوهات", "video", "videos"),
    "sticker": ("ستكر", "ستيكر", "ستيكرات", "sticker", "stickers"),
    "animation": ("جيف", "gif", "gifs"),
    "voice": ("فويس", "فويسات", "voice", "voices", "رسالة صوتية"),
    "audio": ("صوت", "audio", "music", "موسيقى"),
}
REQUEST_WORDS = ("ارسل", "أرسل", "ارسلي", "أرسلي", "بعت", "ابعث", "ابعت", "send", "show", "هات", "جيب", "وريني", "عطني", "اعطني")


def _fallback_reply() -> str:
    return random.choice(RANDOM_REPLIES)


def _requested_media_type(text: str) -> str | None:
    t=(text or "").strip().lower()
    if not t or not any(w in t for w in REQUEST_WORDS):
        return None
    for media_type, words in MEDIA_WORDS.items():
        if any(w in t for w in words):
            return media_type
    return None


def _send_requested_media(handlers, message, media_type: str) -> bool:
    try:
        ref = handlers.rt.images.choose(message.chat.id, media_type)
        if not ref and media_type == "animation":
            ref = handlers.rt.images.choose(message.chat.id, "animation")
        if not ref:
            return False
        sender = {
            "photo": handlers.bot.send_photo,
            "video": handlers.bot.send_video,
            "sticker": handlers.bot.send_sticker,
            "animation": handlers.bot.send_animation,
            "audio": handlers.bot.send_audio,
            "voice": handlers.bot.send_voice,
        }.get(ref.media_type)
        if not sender:
            return False
        sender(message.chat.id, ref.telegram_file_id, reply_to_message_id=message.message_id, allow_sending_without_reply=True)
        handlers.rt.images.mark_used(ref)
        return True
    except Exception:
        log.exception("explicit media request failed")
        return False


def _install_ai_fallback(handlers) -> None:
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


def _background_analyze(handlers, message, user_text: str, bot_reply: str) -> None:
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
        def worker():
            try:
                prompt=("Extract only stable, useful facts explicitly stated in this short group exchange. "
                        "Do not store jokes, insults, secrets, credentials, contact data, or one-off claims. "
                        "Return JSON only: {\"memories\":[{\"key\":\"short_key\",\"value\":\"short fact\"}]}.\n\n"
                        f"USER: {user_text[:700]}\nMERVA: {bot_reply[:500]}")
                result=ai.generate_structured(prompt,{"type":"object","properties":{"memories":{"type":"array"}}},system="You are Merva's background memory analyst. Be conservative; empty memories is valid.")
                if not isinstance(result,dict): return
                store=MemoryStore(handlers.rt.db)
                for item in (result.get("memories") or [])[:2]:
                    if not isinstance(item,dict): continue
                    key=str(item.get("key") or "").strip()[:100]; value=str(item.get("value") or "").strip()
                    if key and value and len(value)<=500:
                        store.remember(message.chat.id,message.from_user.id,value,memory_key="auto:"+key,memory_type="ai")
            except Exception:
                log.debug("Merva background analysis skipped",exc_info=True)
        threading.Thread(target=worker,name="merva-memory-analysis",daemon=True).start()
    except Exception:
        log.debug("could not schedule background analysis",exc_info=True)


def _install_reply_extras(handlers) -> None:
    original=getattr(handlers,"_remember_bot_reply",None)
    if not callable(original) or getattr(handlers,"_social_extras_installed",False): return
    def wrapped(instance,message,text,reply_to=None):
        result=original(message,text,reply_to)
        try:
            user_text=(getattr(message,"text",None) or "").strip()
            if user_text and text: _background_analyze(instance,message,user_text,str(text))
        except Exception: pass
        return result
    handlers._remember_bot_reply=types.MethodType(wrapped,handlers)
    handlers._social_extras_installed=True


def install(handlers) -> None:
    """AI-first social layer. Explicit media requests are fulfilled from the group media pool."""
    original=handlers.on_message
    _install_ai_fallback(handlers)
    _install_reply_extras(handlers)
    def wrapped(message):
        try:
            text=(getattr(message,"text",None) or "").strip()
            if (getattr(message,"from_user",None) and is_group(getattr(message.chat,"type", ""))
                and not getattr(message.from_user,"is_bot",False) and text and not text.startswith("/")):
                requested=_requested_media_type(text)
                if requested and _send_requested_media(handlers,message,requested):
                    return
                # No scripted 12% branch: every normal message goes to the conversation-aware AI.
        except Exception:
            log.exception("social media request layer failed; falling back to AI")
        return original(message)
    handlers.on_message=wrapped
