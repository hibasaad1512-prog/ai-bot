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

# No random text fallback: a failed AI call must never turn into an unrelated
# joke/emoji that looks like a broken response.
ANALYSIS_EVERY = 12
ANALYSIS_COOLDOWN = 180

MEDIA_WORDS = {
    "photo": ("صورة", "صور", "صوره", "صويرة", "photo", "photos", "pic", "pics"),
    "video": ("فيديو", "فيديوهات", "video", "videos"),
    "sticker": ("ستكر", "ستيكر", "ستيكرات", "sticker", "stickers"),
    "animation": ("جيف", "gif", "gifs"),
    "voice": ("فويس", "فويسات", "voice", "voices", "رسالة صوتية"),
    "audio": ("صوت", "audio", "music", "موسيقى"),
}
REQUEST_WORDS = ("ارسل", "أرسل", "ارسلي", "أرسلي", "ترسل", "ترسلي", "رسل", "رسلي", "بعت", "ابعث", "ابعثي", "ابعت", "send", "show", "هات", "جيب", "وريني", "عطني", "اعطني")


def _requested_media_type(text: str) -> str | None:
    t=(text or "").strip().lower()
    if not t or not any(w in t for w in REQUEST_WORDS): return None
    for media_type, words in MEDIA_WORDS.items():
        if any(w in t for w in words): return media_type
    return None


def _send_requested_media(handlers, message, media_type: str) -> bool:
    try:
        ref=handlers.rt.images.choose(message.chat.id, media_type)
        if not ref:return False
        sender={"photo":handlers.bot.send_photo,"video":handlers.bot.send_video,"sticker":handlers.bot.send_sticker,"animation":handlers.bot.send_animation,"audio":handlers.bot.send_audio,"voice":handlers.bot.send_voice}.get(ref.media_type)
        if not sender:return False
        sender(message.chat.id,ref.telegram_file_id,reply_to_message_id=message.message_id,allow_sending_without_reply=True)
        handlers.rt.images.mark_used(ref); return True
    except Exception:
        log.debug("explicit media request failed",exc_info=True); return False


def _install_ai_fallback(handlers) -> None:
    ai=getattr(getattr(handlers,"rt",None),"ai",None)
    if ai is None or getattr(ai,"_social_mix_fallback_installed",False):return
    original=getattr(ai,"generate_text",None)
    if not callable(original):return
    def safe_generate(instance,prompt,system=None):
        try:
            result=original(prompt,system); text=str(result or "").strip()
            return text if text and text.lower() not in {"none","null","nil","n/a"} else ""
        except Exception:
            log.debug("AI unavailable; suppressing fallback reply",exc_info=True)
            return ""
    ai.generate_text=types.MethodType(safe_generate,ai); ai._social_mix_fallback_installed=True


def _background_analyze(handlers,message,user_text:str,bot_reply:str)->None:
    try:
        ai=handlers.rt.ai; now=time.time(); state=getattr(handlers,"_merva_analysis_state",{})
        entry=state.get(message.chat.id,{"count":0,"last":0}); count=int(entry.get("count",0))+1; last=float(entry.get("last",0))
        state[message.chat.id]={"count":count,"last":last}; handlers._merva_analysis_state=state
        if count%ANALYSIS_EVERY!=0 or now-last<ANALYSIS_COOLDOWN:return
        state[message.chat.id]["last"]=now
        def worker():
            try:
                prompt=("Extract only stable, useful facts explicitly stated in this short group exchange. Do not store jokes, insults, secrets, credentials, contact data, or one-off claims. Return JSON only: {\"memories\":[{\"key\":\"short_key\",\"value\":\"short fact\"}]}.\n\n" f"USER: {user_text[:700]}\nMERVA: {bot_reply[:500]}")
                result=ai.generate_structured(prompt,{"type":"object","properties":{"memories":{"type":"array"}}},system="You are Merva's background memory analyst. Be conservative; empty memories is valid.")
                if not isinstance(result,dict):return
                store=MemoryStore(handlers.rt.db)
                for item in (result.get("memories") or [])[:2]:
                    if not isinstance(item,dict):continue
                    key=str(item.get("key") or "").strip()[:100]; value=str(item.get("value") or "").strip()
                    if key and value and len(value)<=500:store.remember(message.chat.id,message.from_user.id,value,memory_key="auto:"+key,memory_type="ai")
            except Exception:log.debug("Merva background analysis skipped",exc_info=True)
        threading.Thread(target=worker,name="merva-memory-analysis",daemon=True).start()
    except Exception:log.debug("could not schedule background analysis",exc_info=True)


def _install_reply_extras(handlers)->None:
    original=getattr(handlers,"_remember_bot_reply",None)
    if not callable(original) or getattr(handlers,"_social_extras_installed",False):return
    def wrapped(instance,message,text,reply_to=None):
        result=original(message,text,reply_to)
        try:
            user_text=(getattr(message,"text",None) or "").strip()
            if user_text and text:_background_analyze(instance,message,user_text,str(text))
        except Exception:pass
        return result
    handlers._remember_bot_reply=types.MethodType(wrapped,handlers); handlers._social_extras_installed=True


def install(handlers)->None:
    """Keep normal chat AI-first; explicit media is handled deterministically by media_requests."""
    original=handlers.on_message
    _install_ai_fallback(handlers); _install_reply_extras(handlers)
    def wrapped(message):
        try:
            text=(getattr(message,"text",None) or "").strip()
            if (getattr(message,"from_user",None) and is_group(getattr(message.chat,"type","")) and not getattr(message.from_user,"is_bot",False) and text and not text.startswith("/")):
                requested=_requested_media_type(text)
                if requested and _send_requested_media(handlers,message,requested):return
        except Exception:log.debug("social media request layer failed",exc_info=True)
        return original(message)
    handlers.on_message=wrapped
