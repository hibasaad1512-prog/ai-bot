from __future__ import annotations
import hashlib, types
from app.config import settings

def _stable_chance(chat_id:int, last_human:float)->float:
    # Deterministic per activity window: restarts cannot reroll the same window.
    payload=f"{chat_id}:{int(last_human)}".encode()
    digest=hashlib.blake2b(payload,digest_size=8).digest()
    return int.from_bytes(digest,"big")/2**64

def install(handlers)->None:
    if getattr(handlers,"_proactive_runtime_installed",False): return
    original=getattr(handlers,"proactive",None); runtime=getattr(handlers,"rt",None)
    if not callable(original) or runtime is None:return
    def wrapped(instance,chat_id:int):
        chat_id=int(chat_id)
        if not runtime.proactive_due(chat_id):return
        state=runtime._proactive_state(chat_id); last_human=float(state.get("last_human",0) or 0)
        # One deterministic roll per activity window. It survives redeploys.
        if _stable_chance(chat_id,last_human)>=float(settings.proactive_chance):
            runtime.mark_proactive_done(chat_id); return
        try:
            next_map=getattr(instance,"_next_proactive",None)
            if isinstance(next_map,dict): next_map[chat_id]=0
            original(chat_id)
        finally: runtime.mark_proactive_done(chat_id)
    handlers.proactive=types.MethodType(wrapped,handlers); handlers._proactive_runtime_installed=True
