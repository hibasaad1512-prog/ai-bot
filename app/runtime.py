from __future__ import annotations
import logging, random, time
from pathlib import Path
from app.config import settings
from app.database import Database
from app.memory.context import ContextStore
from app.images.pool import ImagePool
from app.ai.gemini import GeminiProvider
from app.chaos.engine import ChaosEngine
from app.chaos.personality import Personality
from app.games.engine import GameEngine
from app.games.points import Points
from app.moderation.detector import ModerationDetector
from app.moderation.rules import ModerationPolicy

log=logging.getLogger(__name__)
class Runtime:
    def __init__(self):
        self.db=Database(settings.database_url)
        self.memory=ContextStore(settings.memory_size,settings.memory_ttl_seconds)
        self.images=ImagePool(settings.image_pool_ttl_seconds)
        self.ai=GeminiProvider()
        self.chaos=ChaosEngine()
        self.games=GameEngine(Points(self.db))
        self.moderation=ModerationDetector(ModerationPolicy(settings.enabled_moderation))
        self.personalities:dict[int,Personality]={}
        self.last_proactive=0.0
        self.language_modes:dict[int,str]={}
    def personality(self,chat_id:int)->Personality:
        p=self.personalities.get(chat_id)
        if p:return p
        data=self.db.get_json("chat_settings","chat_id",chat_id,{})
        p=Personality.from_dict(data.get("personality",{})); self.personalities[chat_id]=p; return p
    def get_language_mode(self,chat_id:int)->str:
        if chat_id in self.language_modes:
            return self.language_modes[chat_id]
        data=self.db.get_json("chat_settings","chat_id",chat_id,{})
        mode=str(data.get("language_mode","auto"))
        self.language_modes[chat_id]=mode
        return mode

    def save_language_mode(self,chat_id:int,mode:str)->None:
        mode=mode if mode in {"auto","en","ar","ar-MA","fr","es","tr","de","it","ja","ko","zh"} else "auto"
        data=self.db.get_json("chat_settings","chat_id",chat_id,{})
        data["language_mode"]=mode
        self.db.save_chat_settings(chat_id,data)
        self.language_modes[chat_id]=mode

    def save_personality(self,chat_id:int,p:Personality):
        data=self.db.get_json("chat_settings","chat_id",chat_id,{"personality":{}}); data["personality"]=p.to_dict(); self.db.save_chat_settings(chat_id,data); self.personalities[chat_id]=p
