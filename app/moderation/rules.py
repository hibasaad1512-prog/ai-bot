from __future__ import annotations
import re
URL=re.compile(r"https?://|t\.me/",re.I)

class ModerationPolicy:
    def __init__(self,enabled:bool=True): self.enabled=enabled
    def inspect(self,text:str, recent_texts:list[str])->tuple[str,str]|None:
        if not self.enabled:return None
        normalized=text.strip().lower()
        if len(normalized)>1000:return ("warn","message_too_long")
        if URL.search(normalized) and sum(bool(URL.search(x)) for x in recent_texts[-10:])>=4:return ("delete","link_spam")
        recent=[x.strip().lower() for x in recent_texts[-8:] if x.strip()]
        if normalized and recent.count(normalized)>=3:return ("delete","duplicate_spam")
        return None
