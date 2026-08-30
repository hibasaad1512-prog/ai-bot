from __future__ import annotations
import logging, random, time
from app.config import settings
from app.database import Database
from app.memory.context import ContextStore
from app.images.pool import ImagePool
from app.ai.router import MultiProvider
from app.ai.self_learning import SelfLearningMemory
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
        self.memory=ContextStore(settings.memory_size,settings.memory_ttl_seconds,db=self.db)
        self.images=ImagePool(settings.image_pool_ttl_seconds,db=self.db)
        self.ai=MultiProvider(self.db)
        self.learning=SelfLearningMemory(); self.chaos=ChaosEngine(); self.games=GameEngine(Points(self.db))
        self.moderation=ModerationDetector(ModerationPolicy(settings.enabled_moderation))
        self.personalities={}; self.language_modes={}; self.last_proactive={}; self.next_proactive={}
        self.proactive_min_seconds=int(getattr(settings,'proactive_min_interval',21600)); self.proactive_max_seconds=int(getattr(settings,'proactive_max_interval',54000))
        if self.proactive_max_seconds<self.proactive_min_seconds: self.proactive_min_seconds,self.proactive_max_seconds=self.proactive_max_seconds,self.proactive_min_seconds

    @staticmethod
    def _merge_dict(base, override):
        merged=dict(base or {})
        for key,value in (override or {}).items():
            if value is not None: merged[key]=value
        return merged

    def global_personality(self):
        data=self.db.get_json('chat_settings','chat_id',0,{})
        return Personality.from_dict(data.get('personality',{}))

    def personality(self,chat_id):
        p=self.personalities.get(chat_id)
        if p:return p
        global_p=self.global_personality()
        if int(chat_id)==0:
            self.personalities[chat_id]=global_p; return global_p
        data=self.db.get_json('chat_settings','chat_id',chat_id,{})
        # Global personality is the baseline for every group. A group's
        # explicit values override it, so response behavior is consistent
        # everywhere while local tuning remains possible.
        local=Personality.from_dict(data.get('personality',{}))
        base=global_p.to_dict()
        override=data.get('personality',{}) or {}
        p=Personality.from_dict(self._merge_dict(base,override))
        self.personalities[chat_id]=p
        return p

    def save_personality(self,chat_id,p):
        data=self.db.get_json('chat_settings','chat_id',chat_id,{'personality':{}})
        data['personality']=p.to_dict(); self.db.save_chat_settings(chat_id,data); self.personalities[chat_id]=p

    def save_global_personality(self,p):
        data=self.db.get_json('chat_settings','chat_id',0,{'personality':{}})
        data['personality']=p.to_dict(); self.db.save_chat_settings(0,data)
        self.personalities.clear(); self.personalities[0]=p

    def get_language_mode(self,chat_id):
        if chat_id in self.language_modes:return self.language_modes[chat_id]
        if int(chat_id)!=0:
            global_mode=self.get_language_mode(0)
            data=self.db.get_json('chat_settings','chat_id',chat_id,{})
            if 'language_mode' not in data:
                self.language_modes[chat_id]=global_mode; return global_mode
        data=self.db.get_json('chat_settings','chat_id',chat_id,{})
        mode=str(data.get('language_mode','auto')); self.language_modes[chat_id]=mode; return mode

    def save_language_mode(self,chat_id,mode):
        allowed={'auto','en','ar','ar-MA','fr','es','tr','de','it','ja','ko','zh','pt','ru','uk','el','he','hi','ur','id','ms','tl','nl','pl','ro','cs','sk','hu','sv','no','da','fi'}
        if mode not in allowed: mode='auto'
        data=self.db.get_json('chat_settings','chat_id',chat_id,{}); data['language_mode']=mode; self.db.save_chat_settings(chat_id,data); self.language_modes[chat_id]=mode
        if int(chat_id)==0:
            for key in list(self.language_modes):
                if key!=0:self.language_modes.pop(key,None)

    def schedule_proactive(self,chat_id,force=False):
        now=time.time()
        if not force and chat_id in self.next_proactive and now<self.next_proactive[chat_id]:return self.next_proactive[chat_id]
        nxt=now+random.randint(self.proactive_min_seconds,self.proactive_max_seconds); self.next_proactive[chat_id]=nxt; self.last_proactive[chat_id]=now; return nxt
    def proactive_due(self,chat_id):
        if chat_id not in self.next_proactive:self.schedule_proactive(chat_id); return False
        return time.time()>=self.next_proactive[chat_id]
    def mark_proactive_done(self,chat_id):
        now=time.time(); self.last_proactive[chat_id]=now; self.next_proactive[chat_id]=now+random.randint(self.proactive_min_seconds,self.proactive_max_seconds)
    def proactive_remaining(self,chat_id):
        if chat_id not in self.next_proactive:self.schedule_proactive(chat_id)
        return max(0,int(self.next_proactive[chat_id]-time.time()))
