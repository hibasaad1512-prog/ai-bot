from __future__ import annotations
from telebot import types
from app.telegram.memory_admin import is_owner

def _root(db): return db.get_json('chat_settings','chat_id',0,{})
def _save_root(db,s): db.save_chat_settings(0,s)
def _defaults(db):
    root=_root(db); d=dict(root.get('media_defaults') or {})
    d.setdefault('auto_media_enabled',True); d.setdefault('auto_media_interval_min',120); d.setdefault('auto_media_interval_max',300)
    d.setdefault('active_media_enabled',True); d.setdefault('auto_media_delete_after_send',False); d.setdefault('media_requests_enabled',True)
    root['media_defaults']=d; _save_root(db,root); return d

def _state(db,cid): return db.get_json('chat_state','chat_id',int(cid),{})
def _save(db,cid,**changes):
    s=_state(db,cid); s.update(changes); db.save_state(int(cid),s); return s

def _chats(db):
    root=_root(db); known={}; memberships=root.get('bot_memberships',{})
    for x in root.get('known_chats',[]):
        try: cid=int(x.get('chat_id'))
        except Exception: continue
        if cid>=0 or (str(cid) in memberships and not memberships[str(cid)]): continue
        known[cid]=x
    for cid in db.list_chat_ids():
        try: cid=int(cid)
        except Exception: continue
        if cid>=0 or (str(cid) in memberships and not memberships[str(cid)]): continue
        known.setdefault(cid,{'chat_id':cid,'title':None})
    return list(known.values())

def _apply_all(db,**changes):
    for x in _chats(db):
        try: _save(db,int(x['chat_id']),**changes)
        except Exception: pass

def _fmt(s,title='GROUP'):
    return (f'🎬 MEDIA SETTINGS — {title}\n\n'
            f'🖼 Automatic media: {"ON 🟢" if s.get("auto_media_enabled") else "OFF 🔴"}\n'
            f'⚡ Active pulse: {"ON 🟢" if s.get("active_media_enabled") else "OFF 🔴"}\n'
            f'⏱ Interval: {int(s.get("auto_media_interval_min",120))}–{int(s.get("auto_media_interval_max",300))} minutes\n'
            f'🗑 Delete after send: {"ON 🟢" if s.get("auto_media_delete_after_send") else "OFF 🔴"}\n'
            f'📩 Explicit media requests: {"ON 🟢" if s.get("media_requests_enabled",True) else "OFF 🔴"}\n')

def _kb(db,cid,back='mediaadmin:home'):
    s=_state(db,cid); kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton(f'🖼 Auto: {"ON" if s.get("auto_media_enabled",True) else "OFF"}',callback_data=f'mediaadmin:toggle:{cid}'),types.InlineKeyboardButton(f'⚡ Pulse: {"ON" if s.get("active_media_enabled",True) else "OFF"}',callback_data=f'mediaadmin:pulse:{cid}'))
    kb.add(types.InlineKeyboardButton('⏱ Interval',callback_data=f'mediaadmin:interval:{cid}'),types.InlineKeyboardButton(f'🗑 Delete: {"ON" if s.get("auto_media_delete_after_send",False) else "OFF"}',callback_data=f'mediaadmin:delete:{cid}'))
    kb.add(types.InlineKeyboardButton(f'📩 Requests: {"ON" if s.get("media_requests_enabled",True) else "OFF"}',callback_data=f'mediaadmin:requests:{cid}'))
    kb.add(types.InlineKeyboardButton('⬅️ Back',callback_data=back)); return kb

def register(bot,runtime):
    db=runtime.db
    def show(c,cid=None,global_mode=False):
        if global_mode:
            s=_defaults(db); text=_fmt(s,'GLOBAL — ALL GROUPS')+'\nGlobal changes apply to all known groups and are also the defaults for new groups.'
            kb=types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton(f'🖼 Auto: {"ON" if s.get("auto_media_enabled") else "OFF"}',callback_data='mediaadmin:global_toggle'),types.InlineKeyboardButton(f'⚡ Pulse: {"ON" if s.get("active_media_enabled") else "OFF"}',callback_data='mediaadmin:global_pulse'))
            kb.add(types.InlineKeyboardButton('⏱ Interval',callback_data='mediaadmin:global_interval'),types.InlineKeyboardButton(f'🗑 Delete: {"ON" if s.get("auto_media_delete_after_send") else "OFF"}',callback_data='mediaadmin:global_delete'))
            kb.add(types.InlineKeyboardButton(f'📩 Requests: {"ON" if s.get("media_requests_enabled",True) else "OFF"}',callback_data='mediaadmin:global_requests'),types.InlineKeyboardButton('⬅️ Media Settings',callback_data='mediaadmin:home'))
            bot.edit_message_text(text,c.message.chat.id,c.message.message_id,reply_markup=kb); return
        cid=int(cid); s=_state(db,cid); d=_defaults(db)
        for k in ('auto_media_enabled','active_media_enabled','auto_media_interval_min','auto_media_interval_max','auto_media_delete_after_send','media_requests_enabled'): s.setdefault(k,d[k])
        db.save_state(cid,s); title=next((str(x.get('title') or '') for x in _chats(db) if int(x['chat_id'])==cid),str(cid))
        bot.edit_message_text(_fmt(s,title[:50]),c.message.chat.id,c.message.message_id,reply_markup=_kb(db,cid,'mediaadmin:groups'))

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('mediaadmin:'))
    def callbacks(c):
        if not is_owner(getattr(c.from_user,'id',None)): bot.answer_callback_query(c.id,'Owner only',show_alert=True); return
        try:
            d=c.data
            if d=='mediaadmin:home':
                kb=types.InlineKeyboardMarkup(row_width=1); kb.add(types.InlineKeyboardButton('🌐 Global settings — ALL groups',callback_data='mediaadmin:global')); kb.add(types.InlineKeyboardButton('🎯 Settings for ONE group',callback_data='mediaadmin:groups')); kb.add(types.InlineKeyboardButton('⬅️ GOD PANEL',callback_data='owner:back'))
                bot.edit_message_text('🎬 MEDIA CONTROL\n\nGlobal settings affect all known groups. Per-group settings can then be changed separately.',c.message.chat.id,c.message.message_id,reply_markup=kb); return
            if d=='mediaadmin:global': show(c,global_mode=True); return
            if d=='mediaadmin:groups':
                kb=types.InlineKeyboardMarkup(row_width=1)
                for x in _chats(db):
                    cid=int(x['chat_id']); kb.add(types.InlineKeyboardButton(f'🎯 {str(x.get("title") or f"Group {cid}")[:50]}',callback_data=f'mediaadmin:group:{cid}'))
                kb.add(types.InlineKeyboardButton('🌐 Global settings',callback_data='mediaadmin:global')); kb.add(types.InlineKeyboardButton('⬅️ Media Settings',callback_data='mediaadmin:home'))
                bot.edit_message_text('🎯 SELECT GROUP\n\nChoose exactly one group to edit.',c.message.chat.id,c.message.message_id,reply_markup=kb); return
            if d.startswith('mediaadmin:group:'): show(c,int(d.split(':')[-1])); return
            if d.startswith('mediaadmin:global_'):
                action=d.split('_',1)[1]; s=_defaults(db); key={'toggle':'auto_media_enabled','pulse':'active_media_enabled','delete':'auto_media_delete_after_send','requests':'media_requests_enabled'}.get(action)
                if key:
                    s[key]=not bool(s.get(key)); root=_root(db); root['media_defaults']=s; _save_root(db,root); _apply_all(db,**{key:s[key]}); show(c,global_mode=True); return
                if action=='interval': bot.answer_callback_query(c.id,'اكتب في الخاص: /adminmedia 120 300',show_alert=True); return
            if d.startswith('mediaadmin:'):
                _,action,cid=d.split(':',2); cid=int(cid); s=_state(db,cid)
                if action=='toggle': _save(db,cid,auto_media_enabled=not bool(s.get('auto_media_enabled',True)))
                elif action=='pulse': _save(db,cid,active_media_enabled=not bool(s.get('active_media_enabled',True)))
                elif action=='delete': _save(db,cid,auto_media_delete_after_send=not bool(s.get('auto_media_delete_after_send',False)))
                elif action=='requests': _save(db,cid,media_requests_enabled=not bool(s.get('media_requests_enabled',True)))
                elif action=='interval': bot.answer_callback_query(c.id,'اكتب في الخاص: /adminmedia GROUP_ID 120 300',show_alert=True); return
                title=next((str(x.get('title') or '') for x in _chats(db) if int(x['chat_id'])==cid),str(cid)); s=_state(db,cid); bot.edit_message_text(_fmt(s,title[:50]),c.message.chat.id,c.message.message_id,reply_markup=_kb(db,cid,'mediaadmin:groups')); bot.answer_callback_query(c.id); return
            bot.answer_callback_query(c.id)
        except Exception: bot.answer_callback_query(c.id,'Media settings error',show_alert=True)

    @bot.message_handler(commands=['adminmedia'])
    def adminmedia_command(m):
        if not is_owner(getattr(m.from_user,'id',None)) or getattr(m.chat,'type','')!='private': return
        args=(getattr(m,'text','') or '').split()[1:]
        if len(args)==3:
            try:
                cid=int(args[0]); lo=max(1,min(10080,int(args[1]))); hi=max(lo,min(10080,int(args[2]))); _save(db,cid,auto_media_interval_min=lo,auto_media_interval_max=hi,auto_media_next_at=0); bot.send_message(m.chat.id,f'✅ Group {cid}: interval set to {lo}–{hi} minutes.'); return
            except Exception: bot.send_message(m.chat.id,'❌ Usage: /adminmedia GROUP_ID 120 300'); return
        if len(args)==2:
            try:
                lo=max(1,min(10080,int(args[0]))); hi=max(lo,min(10080,int(args[1]))); d=_defaults(db); d['auto_media_interval_min']=lo; d['auto_media_interval_max']=hi; root=_root(db); root['media_defaults']=d; _save_root(db,root); _apply_all(db,auto_media_interval_min=lo,auto_media_interval_max=hi,auto_media_next_at=0); bot.send_message(m.chat.id,f'✅ Global interval for all known groups: {lo}–{hi} minutes.'); return
            except Exception: pass
        kb=types.InlineKeyboardMarkup(row_width=1); kb.add(types.InlineKeyboardButton('🌐 Global settings',callback_data='mediaadmin:global')); kb.add(types.InlineKeyboardButton('🎯 One specific group',callback_data='mediaadmin:groups')); bot.send_message(m.chat.id,'🎬 MEDIA CONTROL\n\n/adminmedia 120 300 → all groups\n/adminmedia GROUP_ID 120 300 → one group',reply_markup=kb)
