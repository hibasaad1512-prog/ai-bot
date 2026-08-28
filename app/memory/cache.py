from __future__ import annotations
import json, time
class TTLCache:
    def __init__(self): self.data:dict[str,tuple[float,object]]={}
    def set(self,key:str,value,ttl:float)->None:self.data[key]=(time.time()+ttl,value)
    def get(self,key:str):
        item=self.data.get(key)
        if not item:return None
        if item[0]<time.time():self.data.pop(key,None);return None
        return item[1]
