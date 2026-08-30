from __future__ import annotations
import json, logging, os, re, time
from pathlib import Path
log=logging.getLogger(__name__)

class SelfLearningMemory:
    DEFAULT_PATH='data/lmyrfawya_learning.json'
    EMOJI_ALIASES={'😂':'DISCOURAGED','🤣':'DISCOURAGED','😹':'LAUGH','😭':'EMOTIONAL','💀':'DEAD_LAUGH','😼':'MISCHIEVOUS','😻':'AFFECTION','🥺':'SHY','👀':'CURIOUS','❤️':'LOVE','🔥':'HYPE','🐱':'CAT','👍':'APPROVAL','👏':'CLAP','🤔':'THINKING'}
    def __init__(self,path=None,max_users=500,max_facts_per_user=30,max_phrases_per_user=40):
        self.path=Path(path or os.getenv('SELF_LEARNING_PATH',self.DEFAULT_PATH)); self.max_users=int(max_users); self.max_facts_per_user=int(max_facts_per_user); self.max_phrases_per_user=int(max_phrases_per_user); self.data={'version':2,'updated_at':time.time(),'groups':{}}; self._load()
    def _load(self):
        try:
            if self.path.exists():
                x=json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(x,dict): self.data=x
        except Exception: log.exception('self-learning memory load failed')
    def _save(self):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True); self.data['updated_at']=time.time(); tmp=self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data,ensure_ascii=False,indent=2,default=str),encoding='utf-8'); tmp.replace(self.path)
        except Exception: log.exception('self-learning memory save failed')
    def _group(self,cid):
        g=self.data.setdefault('groups',{}).setdefault(str(cid),{'facts':[],'words':{},'phrases':{},'emojis':{},'users':{}}); return g
    def _user(self,cid,uid):
        g=self._group(cid); return g.setdefault('users',{}).setdefault(str(uid),{'name':'','facts':[],'preferences':[],'words':{},'phrases':{},'emojis':{},'style':{},'message_count':0,'last_seen':0})
    @staticmethod
    def _words(text): return re.findall(r'\b[\wÀ-ÿ\u0600-\u06FF]+\b',str(text).lower(),re.UNICODE)
    @classmethod
    def _emojis(cls,text): return [c for c in str(text) if c in cls.EMOJI_ALIASES]
    @staticmethod
    def _add(d,k,n=1): d[str(k)]=int(d.get(str(k),0))+n
    def learn_message(self,chat_id,user_id,display_name,text):
        text=str(text or '').strip()
        if not text:return
        g=self._group(chat_id); u=self._user(chat_id,user_id); u['name']=display_name or u.get('name','user'); u['message_count']=int(u.get('message_count',0))+1; u['last_seen']=time.time()
        for w in self._words(text):
            if len(w)>=2:self._add(u['words'],w); self._add(g['words'],w)
        for e in self._emojis(text): self._add(u['emojis'],e); self._add(g['emojis'],e)
        if '?' in text or '؟' in text:u.setdefault('style',{})['question_rate']=1
        if len(u['facts'])<self.max_facts_per_user:
            m=re.search(r'(?:اسمي|أنا اسمي|انا اسمي|كنحب|كنبغي|أحب|احب)\s+(.{2,80})',text,re.I)
            if m:
                value=m.group(1).strip(' .,!؟،:;\"\''); kind='name' if 'اسمي' in m.group(0) else 'likes';
                if not any(x.get('value','').lower()==value.lower() for x in u['facts']):u['facts'].append({'type':kind,'value':value,'confidence':0.65,'updated_at':time.time()})
        self._trim(g); self._save()
    def _trim(self,g):
        for key in ('words','phrases','emojis'):
            d=g.get(key,{})
            if isinstance(d,dict) and len(d)>100:g[key]=dict(sorted(d.items(),key=lambda x:int(x[1]),reverse=True)[:100])
        users=g.get('users',{})
        if len(users)>self.max_users:g['users']=dict(sorted(users.items(),key=lambda x:float(x[1].get('last_seen',0)),reverse=True)[:self.max_users])
    def remember_fact(self,chat_id,user_id,fact,fact_type='fact',confidence=0.8):
        u=self._user(chat_id,user_id); fact=str(fact or '').strip()
        if fact and not any(x.get('value','').lower()==fact.lower() for x in u['facts']):u['facts'].append({'type':fact_type,'value':fact,'confidence':float(confidence),'updated_at':time.time()}); u['facts']=u['facts'][-self.max_facts_per_user:]; self._save()
    def remember_group_fact(self,chat_id,fact,fact_type='group_fact',confidence=0.8):
        g=self._group(chat_id); fact=str(fact or '').strip()
        if fact and not any(x.get('value','').lower()==fact.lower() for x in g['facts']):g['facts'].append({'type':fact_type,'value':fact,'confidence':float(confidence),'updated_at':time.time()}); g['facts']=g['facts'][-50:]; self._save()
    def get_user_memory(self,cid,uid): return self._user(cid,uid)
    def get_group_memory(self,cid):
        g=self._group(cid); top=lambda d,n:[{'value':k,'count':int(v)} for k,v in sorted(d.items(),key=lambda x:int(x[1]),reverse=True)[:n]]
        return {'facts':g.get('facts',[])[-30:],'top_words':top(g.get('words',{}),20),'top_phrases':top(g.get('phrases',{}),15),'frequent_emojis':top(g.get('emojis',{}),15)}
    def preferred_emojis(self,chat_id,limit=6):
        out=[x['value'] for x in self.get_group_memory(chat_id)['frequent_emojis'] if x['value'] not in ('😂','🤣')];
        if '😹' not in out:out.append('😹')
        return out[:limit]
    def prompt_summary(self,cid,uid=None):
        out=['SELF-LEARNED GROUP MEMORY:',json.dumps(self.get_group_memory(cid),ensure_ascii=False,default=str)]
        if uid is not None:out += ['', 'SELF-LEARNED USER MEMORY:',json.dumps(self.get_user_memory(cid,uid),ensure_ascii=False,default=str)]
        out += ['', 'EMOJI RULE: Avoid 😂 and 🤣; prefer 😹 only when it naturally fits.']
        return '\n'.join(out)
    def export(self,cid): return {'chat_id':cid,'memory':self._group(cid)}
    def clear_user(self,cid,uid): self._group(cid).get('users',{}).pop(str(uid),None); self._save()
    def clear_group(self,cid): self.data.get('groups',{}).pop(str(cid),None); self._save()
