from __future__ import annotations
from telebot import types
from app.telegram.memory_admin import is_owner, menu, chat_menu, provider_menu, provider_actions
PROVIDERS=['groq','gemini','openai','deepseek','openrouter','together']; WAIT={}; OWNER_ID=8734853156

def _state(db): return db.get_json('chat_settings','chat_id',0,{})
def _save(db,s): db.save_chat_settings(0,s)
def _selected(db): return int(_state(db).get('selected_chat_id',0) or 0)
def _chats(db):
    s=_state(db); known={int(x.get('chat_id')):x for x in s.get('known_chats',[]) if str(x.get('chat_id','')).lstrip('-').isdigit()}
    for cid in db.list_chat_ids(): known.setdefault(cid,{'chat_id':cid,'title':f'Chat {cid}'})
    return list(known.values())
def _back(target='owner:back'):
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton('⬅️ Back',callback_data=target)); return k
def _set_lab_target(db,cid):
    s=db.get_json('chat_state','chat_id',OWNER_ID,{})
    s['chaos_target_chat_id']=int(cid); db.save_state(OWNER_ID,s)
def _test_provider(runtime,p):
    runtime.ai.refresh(); keys=runtime.ai.provider_keys(p)
    if not keys:return False,'No saved key'
    names=['groq'] if p=='groq' else [f'{p}:{i+1}' for i in range(len(keys))]
    errors=[]
    for name in names:
        prov=runtime.ai.providers.get(name)
        if not prov or not getattr(prov,'enabled',False):errors.append(f'{name}:not initialized');continue
        try:
            out=prov.generate_text('Reply with exactly: ping',system='Connectivity test. Reply with exactly the requested word.')
            if out:return True,f'Connected successfully ({name})'
            errors.append(f'{name}:empty response')
        except Exception as e:errors.append(f'{name}:{type(e).__name__}')
    return False,'All saved keys failed: '+', '.join(errors[:6])
def register(bot,runtime):
    @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m: bool(getattr(m,'chat',None)) and getattr(m.chat,'type','') in ('group','supergroup'))
    def track_chat(m):
        try:
            s=_state(runtime.db); arr=[x for x in s.get('known_chats',[]) if int(x.get('chat_id',0))!=int(m.chat.id)]
            arr.insert(0,{'chat_id':int(m.chat.id),'title':getattr(m.chat,'title',None),'username':getattr(m.chat,'username',None)})
            s['known_chats']=arr[:200]; _save(runtime.db,s)
        except Exception: pass
    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('owner:'))
    def owner_callback(c):
        if not is_owner(getattr(c.from_user,'id',None)):
            bot.answer_callback_query(c.id,'Not authorized',show_alert=True); return
        d=c.data; uid=int(c.from_user.id)
        try:
            bot.answer_callback_query(c.id)
            if d=='owner:back': bot.edit_message_text('🔐 GOD PANEL',c.message.chat.id,c.message.message_id,reply_markup=menu()); return
            if d=='owner:chats': bot.edit_message_text('🎯 Choose Chat\n\nGroups are detected automatically.',c.message.chat.id,c.message.message_id,reply_markup=chat_menu(_chats(runtime.db),_selected(runtime.db))); return
            if d.startswith('owner:chat:'):
                cid=int(d.split(':')[-1]); s=_state(runtime.db); s['selected_chat_id']=cid; _save(runtime.db,s); _set_lab_target(runtime.db,cid)
                title=next((x.get('title') for x in _chats(runtime.db) if int(x['chat_id'])==cid),f'Chat {cid}')
                bot.edit_message_text(f'🎯 Selected: {title}',c.message.chat.id,c.message.message_id,reply_markup=menu()); return
            if d=='owner:providers': bot.edit_message_text('🔑 AI Providers\n\nKeys are stored persistently in the database. Removing the bot from the app does not delete them or stop saved automation.',c.message.chat.id,c.message.message_id,reply_markup=provider_menu(PROVIDERS)); return
            if d.startswith('owner:provider:'):
                p=d.split(':')[-1]; bot.edit_message_text(f'🔑 {p.title()}\n\nSaved keys: {len(runtime.ai.provider_keys(p))}\n\nKeys survive restarts.',c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
            if d.startswith('owner:padd:'):
                p=d.split(':')[-1]; WAIT[uid]=('add',p); bot.edit_message_text(f'➕ Add {p.title()} API key\n\nSend the key here. It is stored in the database and never echoed.\n\nIt will be tested immediately.',c.message.chat.id,c.message.message_id,reply_markup=_back(f'owner:provider:{p}')); return
            if d.startswith('owner:plist:'):
                p=d.split(':')[-1]; keys=runtime.ai.provider_keys(p); lines=[f'🔑 {p.title()} keys: {len(keys)}']+[f'{i}. {k[:4]}…{k[-4:]}' for i,k in enumerate(keys,1)]; bot.edit_message_text('\n'.join(lines),c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
            if d.startswith('owner:pdelete:'):
                p=d.split(':')[-1]; WAIT[uid]=('delete',p); bot.edit_message_text(f'🗑 Send the {p.title()} key number to delete:',c.message.chat.id,c.message.message_id,reply_markup=_back(f'owner:provider:{p}')); return
            if d.startswith('owner:ptest:'):
                p=d.split(':')[-1]; ok,msg=_test_provider(runtime,p); icon='🟢' if ok else '🔴'; bot.edit_message_text(f'🧪 {p.title()}\n\n{icon} {msg}',c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
        except Exception as e: bot.send_message(c.message.chat.id,f'❌ Admin error: {type(e).__name__}: {str(e)[:160]}')
    @bot.message_handler(content_types=['text'],func=lambda m:is_owner(getattr(m.from_user,'id',None)) and getattr(m.chat,'type','')=='private' and int(getattr(m.from_user,'id',0)) in WAIT)
    def owner_input(m):
        uid=int(m.from_user.id); action,p=WAIT.pop(uid); value=(m.text or '').strip()
        if action=='add':
            if len(value)<8: bot.send_message(m.chat.id,'❌ The API key looks too short.',reply_markup=_back(f'owner:provider:{p}')); return
            ok,reason=runtime.ai.add_provider_key(p,value)
            if not ok: bot.send_message(m.chat.id,f'🔴 Rejected — {reason}',reply_markup=provider_actions(p)); return
            good,msg=_test_provider(runtime,p); icon='🟢' if good else '🔴'
            bot.send_message(m.chat.id,f'💾 Saved permanently: {p.title()}\n{icon} {msg}\n\n🔄 If it fails later, the router tries the next key/provider automatically.',reply_markup=provider_actions(p))
        else:
            try: ok,reason=runtime.ai.delete_provider_key(p,int(value)-1); bot.send_message(m.chat.id,f"{'🗑️ Deleted' if ok else '❌ Failed'} — {reason}",reply_markup=provider_actions(p))
            except: bot.send_message(m.chat.id,'❌ Invalid key number.',reply_markup=provider_actions(p))
