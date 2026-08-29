from __future__ import annotations
import re
from telebot import types
from app.telegram.memory_admin import is_owner, menu, chat_menu, provider_menu, provider_actions

PROVIDERS=['groq','gemini','openai','deepseek','openrouter','together']
WAIT={}

def _state(db): return db.get_json('chat_settings','chat_id',0,{})
def _save(db,s): db.save_chat_settings(0,s)
def _selected(db): return int(_state(db).get('selected_chat_id',0) or 0)
def _chats(db):
    s=_state(db); known={int(x.get('chat_id')):x for x in s.get('known_chats',[]) if str(x.get('chat_id','')).lstrip('-').isdigit()}
    for cid in db.list_chat_ids(): known.setdefault(cid,{'chat_id':cid,'title':f'Chat {cid}'})
    return list(known.values())

def _back():
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton('⬅️ Back',callback_data='owner:back')); return k

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
            if d=='owner:chats':
                bot.edit_message_text('🎯 Choose Chat\n\nThe bot detects groups automatically when it receives messages.',c.message.chat.id,c.message.message_id,reply_markup=chat_menu(_chats(runtime.db),_selected(runtime.db))); return
            if d.startswith('owner:chat:'):
                cid=int(d.split(':')[-1]); s=_state(runtime.db); s['selected_chat_id']=cid; _save(runtime.db,s)
                title=next((x.get('title') for x in _chats(runtime.db) if int(x['chat_id'])==cid),f'Chat {cid}')
                bot.edit_message_text(f'🎯 Selected: {title}',c.message.chat.id,c.message.message_id,reply_markup=menu()); return
            if d=='owner:providers':
                bot.edit_message_text('🔑 AI Providers\n\nChoose the company whose API keys you want to manage.',c.message.chat.id,c.message.message_id,reply_markup=provider_menu(PROVIDERS)); return
            if d.startswith('owner:provider:'):
                p=d.split(':')[-1]; keys=runtime.ai.provider_keys(p); bot.edit_message_text(f'🔑 {p.title()}\n\nKeys saved: {len(keys)}',c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
            if d.startswith('owner:padd:'):
                p=d.split(':')[-1]; WAIT[uid]=('add',p); bot.edit_message_text(f'➕ Add {p.title()} API key\n\nSend the key in this private chat. It will be stored securely in the database and will not be echoed.',c.message.chat.id,c.message.message_id,reply_markup=_back()); return
            if d.startswith('owner:plist:'):
                p=d.split(':')[-1]; keys=runtime.ai.provider_keys(p); lines=[f'🔑 {p.title()} keys: {len(keys)}']
                for i,k in enumerate(keys,1): lines.append(f'{i}. {k[:4]}…{k[-4:]}')
                bot.edit_message_text('\n'.join(lines),c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
            if d.startswith('owner:pdelete:'):
                p=d.split(':')[-1]; WAIT[uid]=('delete',p); bot.edit_message_text(f'🗑 Send the {p.title()} key number to delete:',c.message.chat.id,c.message.message_id,reply_markup=_back()); return
            if d.startswith('owner:ptest:'):
                p=d.split(':')[-1]; keys=runtime.ai.provider_keys(p)
                if not keys: bot.edit_message_text(f'🧪 {p.title()}\n\n❌ No saved key.',c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
                name=f'{p}:1' if p!='groq' else 'groq'; prov=runtime.ai.providers.get(name); text='❌ Test failed'
                if prov:
                    try: text='🟢 Test OK\n\n'+prov.generate_text('Reply with exactly: ping')[:100]
                    except Exception as e:text=f'🔴 Test failed: {type(e).__name__}: {str(e)[:140]}'
                bot.edit_message_text(f'🧪 {p.title()}\n\n{text}',c.message.chat.id,c.message.message_id,reply_markup=provider_actions(p)); return
        except Exception as e:
            bot.send_message(c.message.chat.id,f'❌ Admin error: {type(e).__name__}: {str(e)[:160]}')

    @bot.message_handler(content_types=['text'],func=lambda m: is_owner(getattr(m.from_user,'id',None)) and getattr(m.chat,'type','')=='private' and int(getattr(m.from_user,'id',0)) in WAIT)
    def owner_input(m):
        uid=int(m.from_user.id); action,p=WAIT.pop(uid); value=(m.text or '').strip()
        if action=='add':
            if len(value)<8: bot.send_message(m.chat.id,'❌ The API key looks too short.',reply_markup=_back()); return
            ok,reason=runtime.ai.add_provider_key(p,value); bot.send_message(m.chat.id,f"{'✅ Saved' if ok else '❌ Rejected'} — {reason}",reply_markup=provider_actions(p))
        elif action=='delete':
            try: ok,reason=runtime.ai.delete_provider_key(p,int(value)-1); bot.send_message(m.chat.id,f"{'🗑️ Deleted' if ok else '❌ Failed'} — {reason}",reply_markup=provider_actions(p))
            except: bot.send_message(m.chat.id,'❌ Invalid key number.',reply_markup=provider_actions(p))
