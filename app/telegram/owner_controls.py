from __future__ import annotations
from telebot import types
from app.telegram.memory_admin import is_owner, menu, chat_menu, provider_menu, provider_actions
PROVIDERS=['groq','gemini','openai','deepseek','openrouter','together']; WAIT={}; OWNER_ID=8734853156

def _state(db): return db.get_json('chat_settings','chat_id',0,{})
def _save(db,s): db.save_chat_settings(0,s)
def _selected(db): return int(_state(db).get('selected_chat_id',0) or 0)

def _chats(db):
    s=_state(db); known={}
    for x in s.get('known_chats',[]):
        try: cid=int(x.get('chat_id'))
        except Exception: continue
        if cid not in known or x.get('title'):
            known[cid]={'chat_id':cid,'title':x.get('title'),'username':x.get('username')}
    for cid in db.list_chat_ids():
        try: cid=int(cid)
        except Exception: continue
        known.setdefault(cid,{'chat_id':cid,'title':None,'username':None})
    return list(known.values())

def _refresh_chat_names(bot,db):
    chats=_chats(db); changed=False; out=[]
    for x in chats:
        cid=int(x['chat_id']); title=x.get('title'); username=x.get('username')
        try:
            chat=bot.get_chat(cid)
            fresh_title=getattr(chat,'title',None) or getattr(chat,'first_name',None) or getattr(chat,'last_name',None)
            fresh_username=getattr(chat,'username',None)
            if fresh_title and fresh_title != title: title=fresh_title; changed=True
            if fresh_username and fresh_username != username: username=fresh_username; changed=True
        except Exception: pass
        out.append({'chat_id':cid,'title':title,'username':username})
    if changed:
        s=_state(db); s['known_chats']=out[:200]; _save(db,s)
    return out

def _back(target='owner:back'):
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton('⬅️ Back',callback_data=target)); return k

def _safe_edit(bot, chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
        return True
    except Exception as e:
        if 'message is not modified' in str(e).lower(): return True
        raise

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
        except Exception as e:errors.append(f'{name}:{type(e).__name__}:{str(e)[:100]}')
    return False,'All saved keys failed: '+', '.join(errors[:6])

def register(bot,runtime):
    # Do NOT register a catch-all group message handler here. In pyTelegramBotAPI
    # the first matching handler can consume the update and prevent the AI handler
    # from running. Group discovery is handled by my_chat_member and the archive.
    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('owner:'))
    def owner_callback(c):
        if not is_owner(getattr(c.from_user,'id',None)):
            bot.answer_callback_query(c.id,'Not authorized',show_alert=True); return
        d=c.data; uid=int(c.from_user.id)
        try:
            bot.answer_callback_query(c.id)
            if d in ('owner:back','owner:menu'):
                _safe_edit(bot,c.message.chat.id,c.message.message_id,'🔐 GOD PANEL',reply_markup=menu()); return
            if d in ('owner:chats','owner:chats_refresh'):
                chats=_refresh_chat_names(bot,runtime.db)
                kb=chat_menu(chats,_selected(runtime.db))
                _safe_edit(bot,c.message.chat.id,c.message.message_id,'🎯 Choose Chat\n\nGroups are detected automatically.\nNames are refreshed from Telegram.',reply_markup=kb); return
            if d.startswith('owner:chat:'):
                cid=int(d.split(':')[-1]); s=_state(runtime.db); s['selected_chat_id']=cid; _save(runtime.db,s); _set_lab_target(runtime.db,cid)
                chats=_refresh_chat_names(bot,runtime.db)
                title=next((x.get('title') for x in chats if int(x['chat_id'])==cid),None) or f'Chat {cid}'
                _safe_edit(bot,c.message.chat.id,c.message.message_id,f'🎯 Selected: {title}',reply_markup=menu()); return
            if d.startswith('owner:provider:'):
                p=d.split(':')[-1]; _safe_edit(bot,c.message.chat.id,c.message.message_id,f'🔑 {p.title()}\n\nSaved keys: {len(runtime.ai.provider_keys(p))}\n\nKeys survive restarts. Full key values are never logged.',reply_markup=provider_actions(p)); return
            if d=='owner:providers':
                _safe_edit(bot,c.message.chat.id,c.message.message_id,'🔑 AI Providers\n\nKeys are stored persistently in the database. They are never echoed into logs or error messages.',reply_markup=provider_menu(PROVIDERS)); return
            if d.startswith('owner:padd:'):
                p=d.split(':')[-1]; WAIT[uid]=('add',p); _safe_edit(bot,c.message.chat.id,c.message.message_id,f'➕ Add {p.title()} API key\n\nSend the key here. It is stored in the database and never echoed.\n\nIt will be tested immediately.',reply_markup=_back(f'owner:provider:{p}')); return
            if d.startswith('owner:plist:'):
                p=d.split(':')[-1]; keys=runtime.ai.provider_keys(p); lines=[f'🔑 {p.title()} keys: {len(keys)}']+[f'{i}. {k[:4]}…{k[-4:]}' for i,k in enumerate(keys,1)]; _safe_edit(bot,c.message.chat.id,c.message.message_id,'\n'.join(lines),reply_markup=provider_actions(p)); return
            if d.startswith('owner:pdelete:'):
                p=d.split(':')[-1]; WAIT[uid]=('delete',p); _safe_edit(bot,c.message.chat.id,c.message.message_id,f'🗑 Send the {p.title()} key number to delete:',reply_markup=_back(f'owner:provider:{p}')); return
            if d.startswith('owner:ptest:'):
                p=d.split(':')[-1]; ok,msg=_test_provider(runtime,p); icon='🟢' if ok else '🔴'; _safe_edit(bot,c.message.chat.id,c.message.message_id,f'🧪 {p.title()}\n\n{icon} {msg}',reply_markup=provider_actions(p)); return
        except Exception as e:
            bot.send_message(c.message.chat.id,f'❌ Admin error: {type(e).__name__}: {str(e)[:160]}')
    @bot.message_handler(content_types=['text'],func=lambda m:is_owner(getattr(m.from_user,'id',None)) and getattr(m.chat,'type','')=='private' and int(getattr(m.from_user,'id',0)) in WAIT)
    def owner_input(m):
        uid=int(m.from_user.id); action,p=WAIT.pop(uid); value=(m.text or '').strip()
        if action=='add':
            if len(value)<8: bot.send_message(m.chat.id,'❌ The API key looks too short.',reply_markup=_back(f'owner:provider:{p}')); return
            ok,reason=runtime.ai.add_provider_key(p,value)
            if not ok: bot.send_message(m.chat.id,f'🔴 Rejected — {reason}',reply_markup=provider_actions(p)); return
            good,msg=_test_provider(runtime,p); icon='🟢' if good else '🔴'
            bot.send_message(m.chat.id,f'💾 Saved permanently: {p.title()}\n{icon} {msg}\n\n🔄 If it fails later, the router tries another key/provider automatically.',reply_markup=provider_actions(p))
        else:
            try: ok,reason=runtime.ai.delete_provider_key(p,int(value)-1); bot.send_message(m.chat.id,f"{'🗑️ Deleted' if ok else '❌ Failed'} — {reason}",reply_markup=provider_actions(p))
            except Exception: bot.send_message(m.chat.id,'❌ Invalid key number.',reply_markup=provider_actions(p))
