from __future__ import annotations
import os
from dataclasses import dataclass,field

def env_bool(name,default): return os.getenv(name,str(default)).strip().lower() in {"1","true","yes","on"}
def env_int(name,default,minimum=0):
 try:return max(minimum,int(os.getenv(name,str(default))))
 except (TypeError,ValueError):return default
def env_float(name,default,minimum=0,maximum=None):
 try:v=float(os.getenv(name,str(default)))
 except (TypeError,ValueError):v=default
 v=max(minimum,v); return min(maximum,v) if maximum is not None else v
def env_ids(name):
 out=set()
 for x in os.getenv(name,"").split(","):
  try:
   if x.strip():out.add(int(x.strip()))
  except ValueError:pass
 return frozenset(out)
def env_keys():
 vals=[]; raw=os.getenv("GROQ_API_KEYS","")
 for i,v in enumerate(raw.split(","),1):
  v=v.strip()
  if v: vals.append((i,v)); os.environ.setdefault(f"GROQ_API_KEY_{i}",v)
 for n,v in os.environ.items():
  if n.startswith("GROQ_API_KEY_") and n.rsplit("_",1)[-1].isdigit() and v.strip(): vals.append((int(n.rsplit("_",1)[1]),v.strip()))
 seen={}
 for i,v in vals:seen.setdefault(v,i)
 return tuple(v for v,_ in sorted(seen.items(),key=lambda x:x[1]))
@dataclass(frozen=True)
class PersonalityDefaults:
 chaos:int=env_int("DEFAULT_CHAOS",70,0); humor:int=env_int("DEFAULT_HUMOR",75,0); social:int=env_int("DEFAULT_SOCIAL",80,0); weirdness:int=env_int("DEFAULT_WEIRDNESS",55,0); images:int=env_int("DEFAULT_IMAGES",65,0); events:int=env_int("DEFAULT_EVENTS",50,0); roast:int=env_int("DEFAULT_ROAST",25,0); emoji:int=env_int("DEFAULT_EMOJI",20,0); human_imperfection:int=env_int("DEFAULT_HUMAN_IMPERFECTION",70,0); proactivity:int=env_int("DEFAULT_PROACTIVITY",65,0)
@dataclass(frozen=True)
class Settings:
 telegram_bot_token:str=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); groq_api_key:str=os.getenv("GROQ_API_KEY","").strip(); groq_api_keys:tuple[str,...]=field(default_factory=env_keys); groq_text_model:str=os.getenv("GROQ_TEXT_MODEL","openai/gpt-oss-120b").strip(); openai_api_key:str=os.getenv("OPENAI_API_KEY","").strip(); openai_model:str=os.getenv("OPENAI_MODEL","gpt-4o-mini").strip(); deepseek_api_key:str=os.getenv("DEEPSEEK_API_KEY","").strip(); deepseek_model:str=os.getenv("DEEPSEEK_MODEL","deepseek-chat").strip(); openrouter_api_key:str=os.getenv("OPENROUTER_API_KEY","").strip(); openrouter_model:str=os.getenv("OPENROUTER_MODEL","openai/gpt-4o-mini").strip(); together_api_key:str=os.getenv("TOGETHER_API_KEY","").strip(); together_model:str=os.getenv("TOGETHER_MODEL","meta-llama/Llama-3.3-70B-Instruct-Turbo").strip(); gemini_api_key:str=os.getenv("GEMINI_API_KEY","").strip(); text_model:str=os.getenv("GEMINI_TEXT_MODEL","gemini-2.5-flash").strip(); image_model:str=os.getenv("GEMINI_IMAGE_MODEL","gemini-2.5-flash-image").strip(); ai_provider_order:str=os.getenv("AI_PROVIDER_ORDER","groq,openai,deepseek,openrouter,together,gemini").strip(); groq_admin_ids:frozenset[int]=field(default_factory=lambda:env_ids("GROQ_ADMIN_IDS")); database_url:str=os.getenv("DATABASE_URL","").strip(); redis_url:str=os.getenv("REDIS_URL","").strip(); public_base_url:str=os.getenv("PUBLIC_BASE_URL","").strip().rstrip("/"); webhook_secret:str=os.getenv("WEBHOOK_SECRET","").strip()
 memory_size:int=env_int("CHAT_MEMORY_SIZE",24,10); memory_ttl_seconds:int=env_int("CHAT_MEMORY_TTL_SECONDS",7200,60); image_pool_ttl_seconds:int=env_int("IMAGE_POOL_TTL_SECONDS",21600,300); min_cooldown_seconds:int=env_int("MIN_COOLDOWN_SECONDS",0,0); max_cooldown_seconds:int=env_int("MAX_COOLDOWN_SECONDS",2,0); soft_hourly_limit:int=env_int("SOFT_HOURLY_LIMIT",20,1); hard_hourly_limit:int=env_int("HARD_HOURLY_LIMIT",30,1); max_consecutive_bot_messages:int=env_int("MAX_CONSECUTIVE_BOT_MESSAGES",2,1); max_action_payload_chars:int=env_int("MAX_ACTION_PAYLOAD_CHARS",1200,100); max_image_mb:int=env_int("MAX_IMAGE_MB",8,1)
 enabled_chaos:bool=env_bool("ENABLED_CHAOS",True); enabled_moderation:bool=env_bool("ENABLED_MODERATION",True); enabled_games:bool=env_bool("ENABLED_GAMES",True); enabled_proactive:bool=env_bool("ENABLED_PROACTIVE",True); proactive_min_interval:int=env_int("PROACTIVE_MIN_INTERVAL",14400,60); proactive_max_interval:int=env_int("PROACTIVE_MAX_INTERVAL",43200,60); proactive_chance:float=env_float("PROACTIVE_CHANCE",0.55,0,1); proactive_min_messages:int=env_int("PROACTIVE_MIN_MESSAGES",30,1); proactive_max_messages:int=env_int("PROACTIVE_MAX_MESSAGES",90,1); proactive_idle_seconds:int=env_int("PROACTIVE_IDLE_SECONDS",900,60); proactive_quiet_start:int=env_int("PROACTIVE_QUIET_START",0,0); proactive_quiet_end:int=env_int("PROACTIVE_QUIET_END",6,0); proactive_rest_minutes:int=env_int("PROACTIVE_REST_MINUTES",12,1); proactive_rest_every_hours:int=env_int("PROACTIVE_REST_EVERY_HOURS",6,1)
 reply_chance:float=env_float("REPLY_CHANCE",0.80,0,1); ai_min_score:int=env_int("AI_MIN_SCORE",34,0); callback_min_age_seconds:int=env_int("CALLBACK_MIN_AGE_SECONDS",300,60); proactive_quiet_seconds:int=env_int("PROACTIVE_QUIET_SECONDS",900,60); log_level:str=os.getenv("LOG_LEVEL","INFO").upper(); companion_bot_tokens:tuple[str,...]=field(default_factory=lambda:tuple(x.strip() for x in os.getenv("COMPANION_BOT_TOKENS","").split(",") if x.strip())); defaults:PersonalityDefaults=field(default_factory=PersonalityDefaults)
 def validate(self):
  if not self.telegram_bot_token:raise ValueError("TELEGRAM_BOT_TOKEN is required")
  if self.max_cooldown_seconds<self.min_cooldown_seconds:raise ValueError("MAX_COOLDOWN_SECONDS must be >= MIN_COOLDOWN_SECONDS")
  if self.hard_hourly_limit<self.soft_hourly_limit:raise ValueError("HARD_HOURLY_LIMIT must be >= SOFT_HOURLY_LIMIT")
  if self.proactive_max_interval<self.proactive_min_interval:raise ValueError("PROACTIVE_MAX_INTERVAL must be >= PROACTIVE_MIN_INTERVAL")
  if self.proactive_max_messages<self.proactive_min_messages:raise ValueError("PROACTIVE_MAX_MESSAGES must be >= PROACTIVE_MIN_MESSAGES")
settings=Settings()