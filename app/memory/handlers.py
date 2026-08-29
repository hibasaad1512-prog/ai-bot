from __future__ import annotations
import types
from sqlalchemy import text
from telebot import types as tg_types
from app.memory.store import MemoryStore
from app.telegram.memory_admin import is_owner, menu, memory_menu, key_menu

class MemoryHandlers:
    """Persistent memory plus the private owner-only GOD panel."""
    def __init__(self, bot, runtime, handlers):
        self.bot=bot; self.rt=runtime; self.handlers=handlers
        self.store=MemoryStore(runtime.db)
        self._admin_waiting={}; self._admin_context={}
        self._patch_message_tracking(); self._patch_context(); self._register()

    def _patch_message_tracking(self):
        original=getattr(self.handlers,'on_message',None)
        if not callable(original): return
        store=self.store
        def wrapped(instance,message):
            try:
                u=getattr(message,'from_user',None)
                if u and not getattr(u,'is_bot',False): store.touch_user(int(u.id),getattr(u,'username',None),getattr(u,'first_name',None))
            except Exception: pass
            return original(message)
        self.handlers.on_message=types.MethodType(wrapped,self.handlers)

    def _patch_context(self):
        original=getattr(self.handlers,'_build_ai_context',None)
        if not callable(original): return
        store=self.store
        def wrapped(instance,message,current_text):
            context,mode=original(message,current_text)
            try:
                u=getattr(message,'from_user',None)
                if u:
                    memories=store.search(message.chat.id,u.id,current_text,8) or store.list_memories(message.chat.id,u.id,8)
                    extra=store.format_for_prompt(memories)
                    if extra: context += '\n\n'+extra
            except Exception: pass
            return context,mode
        self.handlers._build_ai_context=types.MethodType(wrapped,self.handlers)

    def _register(self):
        @self.bot.message_handler(commands=['remember'])
        def remember(m):
            if is_owner(getattr(m.from_user,'id',None)): self._remember(m)
        @self.bot.message_handler(commands=['memory'])
        def memory(m):
            if is_owner(getattr(m.from_user,'id',None)): self._list(m)
        @self.bot.message_handler(commands=['forget'])
        def forget(m):
            if is_owner(getattr(m.from_user,'id',None)): self._forget(m)
        @self.bot.message_handler(commands=['clear_memory'])
        def clear(m):
            if is_owner(getattr(m.from_user,'id',None)): self._clear(m)
        @self.bot.message_handler(commands=['admin'])
        def admin(m):
            if is_owner(getattr(m.from_user,'id',None)): self._open_admin(m)
        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('memadmin:'))
        def admin_callback(c):
            if not is_owner(getattr(c.from_user,'id',None)):
                try:self.bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
                except Exception:pass
                return
            try:self._admin_callback(c)
            except Exception:
                try:self.bot.answer_callback_query(c.id,'Operation failed',show_alert=True)
                except Exception:pass
        @self.bot.message_handler(content_types=['text'],func=lambda m:is_owner(getattr(m.from_user,'id',None)) and getattr(m.from_user,'id',None) in self._admin_waiting)
        def admin_input(m): self._handle_admin_input(m)

    def _args(self,m):
        v=getattr(m,'text','') or ''; return v.split(' ',1)[1].strip() if ' ' in v else ''
    def _remember(self,m):
        v=self._args(m)
        if not v:return self.bot.reply_to(m,'Usage: /remember <memory>')
        try:self.store.remember(m.chat.id,m.from_user.id,v); self.bot.reply_to(m,'🧠 Saved permanently.')
        except Exception:self.bot.reply_to(m,'❌ Could not save memory.')
    def _list(self,m):
        try:
            items=self.store.list_memories(m.chat.id,m.from_user.id)
            self.bot.reply_to(m,'🧠 No memories.' if not items else '\n'.join(['🧠 Memories:']+[f"#{x['id']} — {x['memory_value'][:500]}" for x in items[:50]]))
        except Exception:self.bot.reply_to(m,'❌ Could not read memory.')
    def _forget(self,m):
        v=self._args(m)
        if not v:return self.bot.reply_to(m,'Usage: /forget <id or text>')
        try:self.bot.reply_to(m,'🗑 Deleted.' if self.store.forget(m.chat.id,m.from_user.id,v) else 'No matching memory.')
        except Exception:self.bot.reply_to(m,'❌ Could not delete memory.')
    def _clear(self,m):
        try:self.bot.reply_to(m,f'🧹 Deleted {self.store.clear(m.chat.id,m.from_user.id)} memories.')
        except Exception:self.bot.reply_to(m,'❌ Could not clear memory.')
    def _target(self,uid,fallback): return int(self._admin_context.get(uid,fallback))
    def _open_admin(self,m):
        uid=int(m.from_user.id); self._admin_context[uid]=int(m.chat.id)
        self.bot.send_message(uid,'🔐 GOD PANEL',reply_markup=menu()) if m.chat.type!='private' else self.bot.send_message(m.chat.id,'🔐 GOD PANEL',reply_markup=menu())
    def _edit(self,c,text,markup=None):
        try:self.bot.edit_message_text(text,c.message.chat.id,c.message.message_id,reply_markup=markup)
        except Exception:self.bot.send_message(c.message.chat.id,text,reply_markup=markup)
    def _admin_callback(self,c):
        d=c.data; self.bot.answer_callback_query(c.id)
        if d in ('memadmin:home','memadmin:back'): self._edit(c,'🔐 GOD PANEL',menu())
        elif d=='memadmin:memory': self._edit(c,'🧠 Memory',memory_menu())
        elif d=='memadmin:keys': self._edit(c,'🔑 AI Keys',key_menu())
        elif d=='memadmin:listmem': self._admin_list_memory(c)
        elif d=='memadmin:searchmem': self._ask(c,'search_memory','🔎 Send a search term:')
        elif d=='memadmin:addmem': self._ask(c,'add_memory','➕ Send the memory to save:')
        elif d=='memadmin:forgetmem': self._ask(c,'forget_memory','🗑 Send memory ID or text:')
        elif d=='memadmin:clearmem':
            kb=tg_types.InlineKeyboardMarkup(); kb.add(tg_types.InlineKeyboardButton('✅ Delete',callback_data='memadmin:clearmem_yes'),tg_types.InlineKeyboardButton('❌ Cancel',callback_data='memadmin:memory')); self._edit(c,'⚠️ Delete all memories?',kb)
        elif d=='memadmin:clearmem_yes':
            n=self.store.clear(self._target(c.from_user.id,c.message.chat.id),c.from_user.id); self._edit(c,f'🧹 Deleted {n} memories.',memory_menu())
        elif d=='memadmin:messages': self._admin_messages(c)
        elif d=='memadmin:messages_yes':
            target=self._target(c.from_user.id,c.message.chat.id); self._edit(c,f'🧹 Deleted {self.rt.db.delete_messages(target)} stored messages.',menu())
        elif d=='memadmin:media': self._admin_media(c)
        elif d=='memadmin:users': self._admin_users(c)
        elif d in ('memadmin:db','memadmin:status'): self._admin_db(c)
        elif d=='memadmin:settings': self._edit(c,'⚙️ Use Group Settings and Merva Lab for customization.',menu())
        elif d=='memadmin:keylist': self._admin_keys(c)
        elif d=='memadmin:keyadd': self._ask(c,'add_key','🔑 Send the AI API key. It will not be echoed:')
        elif d=='memadmin:keydelete': self._ask(c,'delete_key','🗑 Send the key number to delete:')
        elif d=='memadmin:keytest': self._admin_keytest(c)

    def _ask(self,c,a,p): self._admin_waiting[int(c.from_user.id)]=a; self._edit(c,p)
    def _admin_list_memory(self,c):
        items=self.store.list_memories(self._target(c.from_user.id,c.message.chat.id),c.from_user.id,50); self._edit(c,'🧠 No memories.' if not items else '\n'.join(['🧠 Memories:']+[f"#{x['id']} — {x['memory_value'][:350]}" for x in items]),memory_menu())
    def _admin_messages(self,c):
        target=self._target(c.from_user.id,c.message.chat.id)
        with self.rt.db.engine.connect() as conn:r=conn.execute(text('SELECT COUNT(*) n FROM chat_messages WHERE chat_id=:id'),{'id':target}).mappings().first()
        kb=tg_types.InlineKeyboardMarkup(); kb.add(tg_types.InlineKeyboardButton('🧹 Delete stored messages',callback_data='memadmin:messages_yes')); kb.add(tg_types.InlineKeyboardButton('⬅️ Back',callback_data='memadmin:back')); self._edit(c,f'💬 Stored messages: {int(r["n"] if r else 0)}',kb)
    def _admin_media(self,c):
        target=self._target(c.from_user.id,c.message.chat.id); self._edit(c,f'🖼 Media stored for this group: {self.rt.db.media_count(target)}\nUse Merva Lab or Automation for media actions.',menu())
    def _admin_users(self,c):
        with self.rt.db.engine.connect() as conn:n=conn.execute(text('SELECT COUNT(*) FROM users')).scalar() or 0
        self._edit(c,f'👤 Registered users: {n}',menu())
    def _admin_db(self,c):
        with self.rt.db.engine.connect() as conn:
            u=conn.execute(text('SELECT COUNT(*) FROM users')).scalar() or 0; m=conn.execute(text('SELECT COUNT(*) FROM memory')).scalar() or 0; msg=conn.execute(text('SELECT COUNT(*) FROM chat_messages')).scalar() or 0; media=conn.execute(text('SELECT COUNT(*) FROM media_pool')).scalar() or 0
        self._edit(c,f'🗄 Database OK ✅\nUsers: {u}\nMemories: {m}\nMessages: {msg}\nMedia: {media}',menu())
    def _admin_keys(self,c):
        ai=self.rt.ai; keys=getattr(ai,'keys',[]); lines=[f'🔑 AI keys: {len(keys)}']
        for i,k in enumerate(keys,1):
            masked=ai.mask_key(k) if hasattr(ai,'mask_key') else str(k)[:4]+'…'+str(k)[-4:]; status=getattr(ai,'key_status',{}).get(k,{}).get('status','unknown'); lines.append(f'{i}. {masked} — {status}')
        self._edit(c,'\n'.join(lines),key_menu())
    def _admin_keytest(self,c):
        statuses=[]
        try: statuses=self.rt.ai.get_key_status()
        except Exception: pass
        ready=sum(1 for x in statuses if x.get('status')=='ready'); bad=len(statuses)-ready
        self._edit(c,f'🔄 AI key test\n\n🟢 Ready: {ready}\n🔴 Other/unavailable: {bad}\n📦 Total: {len(statuses)}',key_menu())
    def _handle_admin_input(self,m):
        uid=int(m.from_user.id); action=self._admin_waiting.pop(uid,None); value=(getattr(m,'text','') or '').strip()
        if not action:return
        try:
            target=self._target(uid,m.chat.id)
            if action=='add_memory': self.store.remember(target,uid,value); out='🧠 Saved.'
            elif action=='forget_memory': out=f'🗑 Deleted: {self.store.forget(target,uid,value)}'
            elif action=='search_memory': out='🔎 Results:\n'+'\n'.join(f"#{x['id']} — {x['memory_value'][:500]}" for x in self.store.search(target,uid,value,20))
            elif action=='add_key': ok,status=self.rt.ai.add_key(value); out=f"🔑 {'Added ✅' if ok else 'Rejected ❌'} ({status})"
            elif action=='delete_key': ok=self.rt.ai.delete_key(int(value)-1); out=f"🗑 {'Deleted ✅' if ok else 'Not found ❌'}"
            else: out='❌ Unknown action.'
            self.bot.send_message(m.chat.id,out,reply_markup=menu())
        except Exception:self.bot.send_message(m.chat.id,'❌ Operation failed. No secret was printed.',reply_markup=menu())
