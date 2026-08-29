from __future__ import annotations
import json, random, re
ADMIN_ID = 8734853156

def owner(m):
    u=getattr(m,'from_user',None); c=getattr(m,'chat',None)
    return bool(u and c and c.type=='private' and u.id==ADMIN_ID)

def state(db):
    from sqlalchemy import text
    with db.engine.connect() as c:
        r=c.execute(text('SELECT state_json FROM chat_state WHERE chat_id=:id'),{'id':ADMIN_ID}).mappings().first()
    try:return json.loads(r['state_json']) if r else {}
    except Exception:return {}

def save(db,**kw):
    s=state(db); s.update(kw); db.save_state(ADMIN_ID,s)

def target(db):
    try:return int(state(db).get('chaos_target_chat_id'))
    except Exception:return None

def groups(db):
    from sqlalchemy import text
    with db.engine.connect() as c:
        rows=c.execute(text('SELECT chat_id, COUNT(*) AS messages FROM chat_messages WHERE chat_id < 0 GROUP BY chat_id ORDER BY MAX(timestamp) DESC LIMIT 200')).mappings().all()
    merged={int(x['chat_id']):{'chat_id':int(x['chat_id']),'messages':int(x['messages'])} for x in rows}
    for x in state(db).get('known_chats',[]):
        try:
            cid=int(x['chat_id']); merged[cid]={**merged.get(cid,{'chat_id':cid,'messages':0}),**x,'chat_id':cid}
        except Exception:pass
    return list(merged.values())[:100]

def remember_chat(db,chat):
    known=state(db).get('known_chats',[]); cid=int(chat.id)
    item={'chat_id':cid,'title':getattr(chat,'title',None),'username':getattr(chat,'username',None),'type':getattr(chat,'type',None)}
    known=[x for x in known if int(x.get('chat_id',0))!=cid]; known.insert(0,item); save(db,known_chats=known[:100]); return item

def resolve_text(bot,value):
    value=(value or '').strip()
    if value.startswith('@'): return bot.get_chat(value)
    m=re.search(r't\.me/(?:c/)?([A-Za-z0-9_+\-]+)',value)
    if not m:
        try:return bot.get_chat(int(value))
        except Exception:return None
    token=m.group(1)
    if token.isdigit():return bot.get_chat(int('-100'+token))
    if not token.startswith('+'):return bot.get_chat('@'+token)
    return None

def toks(msgs):
    out=[]
    for m in msgs:out+=re.findall(r'[^\s]{2,24}',getattr(m,'text','') or '')
    return [x for x in out if not x.startswith(('/', 'http://','https://'))]

def menu():
    from telebot import types
    k=types.InlineKeyboardMarkup(row_width=2)
    for a,b in [('🎯 اختيار الكروب','mad:chats'),('➕ تعريف كروب','mad:addchat'),('📨 إرسال مباشر','mad:send'),('🎲 عشوائي','mad:random'),('🧪 خلط كلمات','mad:remix'),('🗳️ استطلاع','mad:poll'),('⭐ Tip عشوائي','mad:tip'),('🎭 رسالة/مود','mad:mood'),('🖼️ وسائط الكروب','mad:media'),('📊 الحالة','mad:status')]:k.add(types.InlineKeyboardButton(a,callback_data=b))
    k.add(types.InlineKeyboardButton('⬅️ لوحة التحكم','mad:god'),types.InlineKeyboardButton('🛑 إيقاف المختبر','mad:disable')); return k

def group_menu(gs):
    from telebot import types
    k=types.InlineKeyboardMarkup(row_width=1)
    if not gs:k.add(types.InlineKeyboardButton('⚠️ لا توجد كروبات معروفة بعد',callback_data='mad:addchat'))
    for g in gs:
        label=g.get('title') or (('@'+g['username']) if g.get('username') else str(g['chat_id']))
        k.add(types.InlineKeyboardButton(f"🎯 {label} · {g.get('messages',0)} رسالة",callback_data=f"mad:select:{g['chat_id']}"))
    k.add(types.InlineKeyboardButton('➕ تعريف كروب',callback_data='mad:addchat'),types.InlineKeyboardButton('🔄 تحديث',callback_data='mad:chats'),types.InlineKeyboardButton('⬅️ رجوع',callback_data='mad:open')); return k

def register(bot,runtime):
    @bot.message_handler(commands=['admin'])
    def admin(m):
        if not owner(m):return
        bot.send_message(m.chat.id,'🔐 GOD PANEL\n\n🧪 مختبر الميرفاوية\nاختر العملية:',reply_markup=menu())
    if not getattr(bot,'_merva_chat_discovery_wrapped',False):
        original=bot.process_new_updates
        def process(updates):
            try:
                for update in updates or []:
                    msg=getattr(update,'message',None) or getattr(update,'edited_message',None) or getattr(update,'channel_post',None)
                    chat=getattr(msg,'chat',None)
                    if chat and getattr(chat,'type',None) in ('group','supergroup'):remember_chat(runtime.db,chat)
            except Exception:pass
            return original(updates)
        bot.process_new_updates=process; bot._merva_chat_discovery_wrapped=True
    @bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('mad:'))
    def cb(c):
        if not getattr(c,'from_user',None) or c.from_user.id!=ADMIN_ID or getattr(c.message.chat,'type',None)!='private':return bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
        d=c.data; t=target(runtime.db)
        try:
            if d=='mad:open' or d=='mad:god':bot.edit_message_text('🔐 GOD PANEL\n\n🧪 مختبر الميرفاوية\nاختر العملية:',c.message.chat.id,c.message.message_id,reply_markup=menu());return
            if d=='mad:chats':bot.edit_message_text('🎯 اختر الكروب:',c.message.chat.id,c.message.message_id,reply_markup=group_menu(groups(runtime.db)));return
            if d=='mad:addchat':save(runtime.db,mad_waiting='addchat');bot.send_message(c.message.chat.id,'➕ أرسل Forward من الكروب أو @username أو chat ID.');return
            if d.startswith('mad:select:'):save(runtime.db,chaos_target_chat_id=int(d.split(':')[-1]),mad_waiting=False);bot.edit_message_text('🎯 تم اختيار الكروب.\n\nاختر العملية:',c.message.chat.id,c.message.message_id,reply_markup=menu());return
            if d=='mad:send':
                if not t:return bot.answer_callback_query(c.id,'اختار كروبًا أولًا',show_alert=True)
                save(runtime.db,mad_waiting='send');bot.send_message(c.message.chat.id,'📨 أرسل الآن أي رسالة أو صورة أو فيديو أو Sticker.');return
            if not t:return bot.answer_callback_query(c.id,'اختار كروبًا أولًا',show_alert=True)
            msgs=runtime.db.recent_messages(t,120)
            if d=='mad:random' and msgs:bot.copy_message(t,t,random.choice(msgs).message_id)
            elif d=='mad:remix':bot.send_message(t,' '.join(random.sample(toks(msgs),min(10,len(toks(msgs))))) if toks(msgs) else '3:')
            elif d=='mad:tip':bot.send_message(t,'3:\n\n⭐ Tip: '+str(random.randint(1,1000)))
            elif d=='mad:mood':bot.send_message(t,random.choice(['3:','المود اليوم غريب شوية','صافي خليوها على الله','كنراقب فقط 👀']))
            elif d=='mad:media':
                media=[m for m in msgs if getattr(m,'media_type',None)]
                if media:bot.copy_message(t,t,random.choice(media).message_id)
                else:return bot.answer_callback_query(c.id,'لا توجد وسائط محفوظة بعد.',show_alert=True)
            elif d=='mad:poll':
                words=list(dict.fromkeys(toks(msgs)))
                if len(words)>=3:bot.send_poll(t,'شنو كلمة اليوم؟',random.sample(words,min(8,len(words))),is_anonymous=True)
                else:return bot.answer_callback_query(c.id,'الكلمات غير كافية.',show_alert=True)
            elif d=='mad:status':bot.edit_message_text(f'🧪 الحالة\n\n🎯 الكروب: {t}\n💬 الكروبات المعروفة: {len(groups(runtime.db))}\n💾 الرسائل: {len(msgs)}',c.message.chat.id,c.message.message_id,reply_markup=menu());return
            elif d=='mad:disable':save(runtime.db,chaos_target_chat_id=None,mad_waiting=False);bot.edit_message_text('🛑 تم إيقاف المختبر.',c.message.chat.id,c.message.message_id,reply_markup=menu());return
            bot.answer_callback_query(c.id,'تم التنفيذ ✅')
        except Exception as e:bot.answer_callback_query(c.id,'Lab error: '+str(e)[:80],show_alert=True)
    @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
    def lab_input(m):
        mode=state(runtime.db).get('mad_waiting'); t=target(runtime.db)
        if mode=='addchat':
            chat=getattr(m,'forward_from_chat',None) or getattr(getattr(m,'forward_origin',None),'chat',None)
            if not chat and getattr(m,'content_type','')=='text':chat=resolve_text(bot,m.text)
            if not chat or getattr(chat,'type','') not in ('group','supergroup'):bot.send_message(m.chat.id,'❌ أرسل Forward من رسالة داخل الكروب.');return
            remember_chat(runtime.db,chat);save(runtime.db,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم حفظ الكروب. اضغط اختيار الكروب.') ;return
        if not t:bot.send_message(m.chat.id,'🎯 اختر كروبًا أولًا');save(runtime.db,mad_waiting=False);return
        try:bot.copy_message(t,m.chat.id,m.message_id);bot.send_message(m.chat.id,'✅ تم الإرسال.');save(runtime.db,mad_waiting=False)
        except Exception as e:bot.send_message(m.chat.id,'❌ '+str(e)[:120]);save(runtime.db,mad_waiting=False)
