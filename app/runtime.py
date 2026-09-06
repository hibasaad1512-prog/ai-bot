from __future__ import annotations
import logging,random,time
from datetime import datetime
from zoneinfo import ZoneInfo
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
  settings.validate(); self.db=Database(settings.database_url); self.memory=ContextStore(settings.memory_size,settings.memory_ttl_seconds,db=self.db); self.images=ImagePool(settings.image_pool_ttl_seconds,db=self.db); self.ai=MultiProvider(self.db); self._secure_ai_status(); self.learning=SelfLearningMemory(); self.chaos=ChaosEngine(); self.games=GameEngine(Points(self.db)); self.moderation=ModerationDetector(ModerationPolicy(settings.enabled_moderation)); self.personalities={}; self.language_modes={}; self.last_proactive={}; self.next_proactive={}; self.proactive_min_seconds=max(60,int(settings.proactive_min_interval)); self.proactive_max_seconds=max(self.proactive_min_seconds,int(settings.proactive_max_interval))
 def _secure_ai_status(self):
  getter=getattr(self.ai,"get_key_status",None)
  if not callable(getter): return
  original=getter
  def safe_status():
   rows=original()
   if not isinstance(rows,list): return rows
   out=[]
   for row in rows:
    item=dict(row) if isinstance(row,dict) else {}; raw=str(item.get("key","")); masked=str(item.get("masked","")); item["key"]=masked or (raw[:4]+"…"+raw[-4:] if len(raw)>10 else "[hidden]"); item.pop("secret",None); out.append(item)
   return out
  self.ai.get_key_status=safe_status
 @staticmethod
 def _merge_dict(base,override):
  d=dict(base or {}); d.update({k:v for k,v in (override or {}).items() if v is not None}); return d
 def global_personality(self): return Personality.from_dict(self.db.get_json("chat_settings","chat_id",0,{}).get("personality",{}))
 def personality(self,chat_id):
  if chat_id in self.personalities:return self.personalities[chat_id]
  g=self.global_personality()
  if int(chat_id)==0:self.personalities[chat_id]=g; return g
  d=self.db.get_json("chat_settings","chat_id",chat_id,{}); p=Personality.from_dict(self._merge_dict(g.to_dict(),Personality.from_dict(d.get("personality",{})).to_dict())); self.personalities[chat_id]=p; return p
 def save_personality(self,chat_id,p):
  d=self.db.get_json("chat_settings","chat_id",chat_id,{"personality":{}}); d["personality"]=p.to_dict(); self.db.save_chat_settings(chat_id,d); self.personalities[chat_id]=p
 def save_global_personality(self,p):
  d=self.db.get_json("chat_settings","chat_id",0,{"personality":{}}); d["personality"]=p.to_dict(); self.db.save_chat_settings(0,d); self.personalities.clear(); self.personalities[0]=p
 def get_language_mode(self,chat_id):
  if chat_id in self.language_modes:return self.language_modes[chat_id]
  if int(chat_id)!=0:
   g=self.get_language_mode(0); d=self.db.get_json("chat_settings","chat_id",chat_id,{})
   if "language_mode" not in d:self.language_modes[chat_id]=g; return g
  d=self.db.get_json("chat_settings","chat_id",chat_id,{}); mode=str(d.get("language_mode","auto")); self.language_modes[chat_id]=mode; return mode
 def save_language_mode(self,chat_id,mode):
  allowed={"auto","en","ar","ar-MA","fr","es","tr","de","it","ja","ko","zh","pt","ru","uk","el","he","hi","ur","id","ms","tl","nl","pl","ro","cs","sk","hu","sv","no","da","fi"}; mode=mode if mode in allowed else "auto"; d=self.db.get_json("chat_settings","chat_id",chat_id,{}); d["language_mode"]=mode; self.db.save_chat_settings(chat_id,d); self.language_modes[chat_id]=mode
  if int(chat_id)==0:
   for k in list(self.language_modes):
    if k!=0:self.language_modes.pop(k,None)
 def _proactive_state(self,chat_id):
  d=self.db.get_json("chat_state","chat_id",chat_id,{}); s=d.get("proactive",{}); return s if isinstance(s,dict) else {}
 def _save_proactive_state(self,chat_id):
  d=self.db.get_json("chat_state","chat_id",chat_id,{}); d["proactive"]={"last":self.last_proactive.get(chat_id),"next":self.next_proactive.get(chat_id),"messages":int(getattr(self,"_proactive_messages",{}).get(chat_id,0)),"target_messages":int(getattr(self,"_proactive_target_messages",{}).get(chat_id,0)),"last_human":getattr(self,"_last_human",{}).get(chat_id)}; self.db.save_state(chat_id,d)
 def _load_smart_state(self,chat_id):
  if not hasattr(self,"_proactive_messages"): self._proactive_messages={}; self._proactive_target_messages={}; self._last_human={}
  if chat_id in self._proactive_messages:return
  s=self._proactive_state(chat_id); self._proactive_messages[chat_id]=int(s.get("messages",0) or 0); self._proactive_target_messages[chat_id]=int(s.get("target_messages",0) or 0); self._last_human[chat_id]=float(s.get("last_human",0) or 0)
  if s.get("last"):self.last_proactive[chat_id]=float(s["last"])
  if s.get("next"):self.next_proactive[chat_id]=float(s["next"])
 def note_human_activity(self,chat_id):
  self._load_smart_state(chat_id); self._proactive_messages[chat_id]+=1; self._last_human[chat_id]=time.time(); self._save_proactive_state(chat_id)
 def _resting_now(self):
  now=datetime.now(ZoneInfo("Africa/Casablanca")); h=now.hour; start=int(settings.proactive_quiet_start)%24; end=int(settings.proactive_quiet_end)%24
  if start!=end and ((start<=h<end) if start<end else (h>=start or h<end)):return True
  every=max(1,int(settings.proactive_rest_every_hours)); minutes=max(1,int(settings.proactive_rest_minutes))
  return (h%every==0 and now.minute<minutes)
 def schedule_proactive(self,chat_id,force=False):
  self._load_smart_state(chat_id); now=time.time()
  if not force and self.next_proactive.get(chat_id,0)>now:return self.next_proactive[chat_id]
  self.next_proactive[chat_id]=now+random.randint(self.proactive_min_seconds,self.proactive_max_seconds); self.last_proactive.setdefault(chat_id,now); self._proactive_target_messages[chat_id]=random.randint(settings.proactive_min_messages,settings.proactive_max_messages); self._save_proactive_state(chat_id); return self.next_proactive[chat_id]
 def proactive_due(self,chat_id):
  self._load_smart_state(chat_id)
  if self._resting_now():return False
  if self._last_human.get(chat_id,0) and time.time()-self._last_human[chat_id]<settings.proactive_idle_seconds:return False
  if chat_id not in self.next_proactive:self.schedule_proactive(chat_id); return False
  return self._proactive_messages.get(chat_id,0)>=max(1,self._proactive_target_messages.get(chat_id,settings.proactive_min_messages)) or time.time()>=self.next_proactive[chat_id]
 def mark_proactive_done(self,chat_id):
  self._load_smart_state(chat_id); now=time.time(); self.last_proactive[chat_id]=now; self.next_proactive[chat_id]=now+random.randint(self.proactive_min_seconds,self.proactive_max_seconds); self._proactive_messages[chat_id]=0; self._proactive_target_messages[chat_id]=random.randint(settings.proactive_min_messages,settings.proactive_max_messages); self._save_proactive_state(chat_id)
 def proactive_remaining(self,chat_id):
  if chat_id not in self.next_proactive:self.schedule_proactive(chat_id)
  return max(0,int(self.next_proactive[chat_id]-time.time()))
