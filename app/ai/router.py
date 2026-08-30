from __future__ import annotations
import json, logging, os, base64, requests
from .base import AIProvider
from .groq import GroqProvider
from .gemini import GeminiProvider
log=logging.getLogger(__name__)
SPECS={'openai':('OPENAI_BASE_URL','OPENAI_MODEL','https://api.openai.com/v1','gpt-4o-mini'),'deepseek':('DEEPSEEK_BASE_URL','DEEPSEEK_MODEL','https://api.deepseek.com/v1','deepseek-chat'),'openrouter':('OPENROUTER_BASE_URL','OPENROUTER_MODEL','https://openrouter.ai/api/v1','openai/gpt-4o-mini'),'together':('TOGETHER_BASE_URL','TOGETHER_MODEL','https://api.together.xyz/v1','meta-llama/Llama-3.3-70B-Instruct-Turbo')}
class OpenAICompatibleProvider(AIProvider):
 def __init__(self,name,api_key,base_url,model): self.name=name; self.api_key=api_key.strip(); self.base_url=base_url.rstrip('/'); self.model=model.strip()
 @property
 def enabled(self): return bool(self.api_key and self.model)
 def _request(self,messages,**extra):
  if not self.enabled: raise RuntimeError(f'{self.name} is not configured')
  r=requests.post(f'{self.base_url}/chat/completions',headers={'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json'},json={'model':self.model,'messages':messages,**extra},timeout=35)
  r.raise_for_status(); data=r.json(); choices=data.get('choices') or []
  if not choices: raise RuntimeError(f'{self.name}: empty response')
  return data
 def _messages(self,prompt,system): return ([{'role':'system','content':system}] if system else [])+[{'role':'user','content':prompt}]
 def generate_text(self,prompt,system=None): return str(self._request(self._messages(prompt,system),temperature=0.65)['choices'][0]['message'].get('content','')).strip()
 def generate_structured(self,prompt,schema,system=None): return json.loads(self._request(self._messages(prompt,system),temperature=0,response_format={'type':'json_object'})['choices'][0]['message'].get('content','{}'))
 def analyze_image(self,image_bytes,prompt):
  b64=base64.b64encode(image_bytes).decode(); msg=[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':f'data:image/jpeg;base64,{b64}'}}]}]; return str(self._request(msg,temperature=0)['choices'][0]['message'].get('content','')).strip()
 def generate_image(self,prompt): return None
class MultiProvider(AIProvider):
 def __init__(self,db): self.db=db; self.groq=GroqProvider(db); self.providers={}; self.order=[]; self.refresh()
 def _state(self):
  try:return self.db.get_json('chat_settings','chat_id',0,{})
  except:return {}
 def _keys(self):
  s=self._state(); data=dict(s.get('ai_keys',{})); data['groq']=list(self.groq.keys); return data
 def refresh(self):
  self.providers={'groq':self.groq}; self.order=[]; saved=self._keys()
  for name,(be,me,bd,md) in SPECS.items():
   keys=list(saved.get(name,[])); env=os.getenv(name.upper()+'_API_KEY','').strip()
   if env and env not in keys: keys.append(env)
   for i,key in enumerate(keys): self.providers[f'{name}:{i+1}']=OpenAICompatibleProvider(name,key,os.getenv(be,bd),os.getenv(me,md))
  gkeys=list(saved.get('gemini',[])); envg=os.getenv('GEMINI_API_KEY','').strip()
  if envg and envg not in gkeys:gkeys.append(envg)
  for i,key in enumerate(gkeys): self.providers[f'gemini:{i+1}']=GeminiProvider(key)
  bases=[x.strip().lower() for x in os.getenv('AI_PROVIDER_ORDER','groq,gemini,openai,deepseek,openrouter,together').split(',') if x.strip()]
  for base in bases:
   if base=='groq': self.order.append('groq')
   else: self.order.extend([k for k in self.providers if k.startswith(base+':')])
  for k in self.providers:
   if k not in self.order:self.order.append(k)
 @property
 def enabled(self): self.refresh(); return any(getattr(self.providers.get(n),'enabled',False) for n in self.order)
 @property
 def keys(self): return self.groq.keys
 @property
 def key_status(self): return self.groq.key_status
 @property
 def current_key_number(self): return self.groq.current_key_number
 def mask_key(self,key): return self.groq.mask_key(key)
 def add_key(self,key): return self.groq.add_key(key)
 def delete_key(self,index): return self.groq.delete_key(index)
 def switch_key(self,index): return self.groq.switch_key(index)
 def provider_names(self): return ['groq','gemini','openai','deepseek','openrouter','together']
 def provider_keys(self,provider): self.refresh(); return list(self._keys().get(provider,[]))
 def add_provider_key(self,provider,key):
  provider=provider.lower().strip(); key=key.strip()
  if provider not in self.provider_names() or not key:return False,'invalid'
  if provider=='groq': return self.groq.add_key(key)
  s=self._state(); data=dict(s.get('ai_keys',{})); arr=list(data.get(provider,[]))
  if key in arr:return False,'already_exists'
  arr.append(key); data[provider]=arr; s['ai_keys']=data; self.db.save_chat_settings(0,s); self.refresh(); return True,'saved'
 def delete_provider_key(self,provider,index):
  provider=provider.lower().strip()
  if provider=='groq': return self.groq.delete_key(index)
  s=self._state(); data=dict(s.get('ai_keys',{})); arr=list(data.get(provider,[]))
  if index<0 or index>=len(arr):return False,'invalid_index'
  arr.pop(index); data[provider]=arr; s['ai_keys']=data; self.db.save_chat_settings(0,s); self.refresh(); return True,'deleted'
 def provider_status(self): self.refresh(); return [(n,bool(getattr(self.providers.get(n),'enabled',False))) for n in self.order]
 def _try(self,method,*args,**kwargs):
  self.refresh(); errors=[]
  for name in self.order:
   p=self.providers.get(name)
   if not p or not getattr(p,'enabled',False):continue
   try:
    r=getattr(p,method)(*args,**kwargs)
    if isinstance(r,str): r=r.strip()
    if r:return r
    errors.append(f'{name}:empty_response')
   except Exception as e:
    errors.append(f'{name}:{type(e).__name__}:{str(e)[:120]}')
    log.warning('AI provider %s failed; trying next',name)
  raise RuntimeError('All configured AI providers failed: '+', '.join(errors))
 def generate_text(self,prompt,system=None): return self._try('generate_text',prompt,system)
 def generate_structured(self,prompt,schema,system=None): return self._try('generate_structured',prompt,schema,system)
 def analyze_image(self,image_bytes,prompt): return self._try('analyze_image',image_bytes,prompt)
 def generate_image(self,prompt):
  self.refresh()
  for name in self.order:
   p=self.providers.get(name)
   if p and getattr(p,'enabled',False):
    try:
     r=p.generate_image(prompt)
     if r:return r
    except Exception: log.warning('AI image provider %s failed',name)
  return None
