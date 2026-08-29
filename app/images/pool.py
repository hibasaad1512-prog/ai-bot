from __future__ import annotations
import random,time
from dataclasses import dataclass

@dataclass(slots=True)
class ImageRef:
    chat_id:int; message_id:int; telegram_file_id:str; created_at:float; used_at:float|None; uploader_id:int; media_type:str

class ImagePool:
    def __init__(self,ttl:float=21600,max_per_chat:int=50): self.ttl=ttl; self.max=max_per_chat; self.data:dict[int,list[ImageRef]]={}
    def add(self,ref:ImageRef)->None:
        q=self.data.setdefault(ref.chat_id,[]); q.append(ref); self.cleanup(ref.chat_id); self.data[ref.chat_id]=q[-self.max:]
    def cleanup(self,chat_id:int)->None:
        cut=time.time()-self.ttl; self.data[chat_id]=[x for x in self.data.get(chat_id,[]) if x.created_at>=cut]
    def choose(self,chat_id:int)->ImageRef|None:
        self.cleanup(chat_id); q=self.data.get(chat_id,[])
        if not q:return None
        unused=[x for x in q if x.used_at is None]; return random.choice(unused or q)
    def mark_used(self,ref:ImageRef)->None: ref.used_at=time.time()
