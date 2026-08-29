from __future__ import annotations
import json, random, re, logging
ADMIN_ID=8734853156

def owner(m):
 u=getattr(m,'from_user',None); c=getattr(m,'chat',None); return bool(u and c and c.type=='private' and int(u.id)==ADMIN_ID)
def state(db):
 from sqlalchemy import text
 with db.engine.connect() as c:r=c.execute(text('SELECT state_json FROM chat_state WHERE chat_id=:id'),{'id':ADMIN_ID}).mappings().first()
 try:return json.loads(r['state_json']) if r else {}
 except:return {}
def save(db,**kw):
 s=state(db);s.update(kw);db.save_state(ADMIN_ID,s)
def target(db):
 try:return int(state(db).get('chaos_target_chat_id'))
 except:return None
def groups(db):
 from sqlalchemy import text
 with db.engine.connect() as c:rows=c.execute(text('SELECT chat_id,COUNT(*) messages FROM chat_messages WHERE chat_id<0 GROUP BY chat_id ORDER BY MAX(timestamp) DESC LIMIT 200')).mappings().all()
 return [{'chat_id':int(x['chat_id']),'messages':int(x['messages'])} for x in rows]
def toks(msgs):
 out=[]
 for m in msgs:out+=re.findall(r'[^\s]{2,24}',getattr(m,'text','') or '')
 return [x for x in out if not x.startswith(('/', 'http://','https://'))]
def menu():
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=2)
 for a,b in [('🎯 اختيار الكروب','mad:chats'),('➕ تعريف كروب','mad:addchat'),('📨 إرسال','mad:send'),('🎲 عشوائي','mad:random'),('🧪 خلط','mad:remix'),('🗳️ استطلاع','mad:poll'),('⭐ Tip','mad:tip'),('🎭 مود','mad:mood'),('🖼️ وسائط','mad:media'),('📊 الحالة','mad:status')]:k.add(types.InlineKeyboardButton(a,callback_data=b))
 k.add(types.InlineKeyboardButton('🛑 إيقاف المختبر',callback_data='mad:disable'));return k
def group_menu(gs):
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=1)
 for g in gs:k.add(types.InlineKeyboardButton(f"🎯 {g['chat_id']} · {g['messages']} رسالة",callback_data=f"mad:select:{g['chat_id']}"))
 k.add(types.InlineKeyboardButton('⬅️ رجوع',callback_data='mad:open'));return k
def register(bot,runtime):
 @bot.message_handler(commands=['admin'])
 def admin(m):
  if owner(m):bot.send_message(m.chat.id,'🔐 GOD PANEL\n\n🧪 مختبر الميرفاوية',reply_markup=menu())
 @bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('mad:'))
 def cb(c):
  if not getattr(c,'from_user',None) or int(c.from_user.id)!=ADMIN_ID or getattr(getattr(c,'message',None),'chat',None).type!='private':
   try:bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
   except:pass
   return
  d=c.data
  try:
   if d=='mad:open':bot.send_message(c.message.chat.id,'🧪 مختبر الميرفاوية',reply_markup=menu());return
   if d=='mad:chats':bot.send_message(c.message.chat.id,'🎯 اختر الكروب:',reply_markup=group_menu(groups(runtime.db)));return
   if d=='mad:addchat':save(runtime.db,mad_waiting='addchat');bot.send_message(c.message.chat.id,'➕ أرسل Forward من الكروب أو chat ID.');return
   if d.startswith('mad:select:'):save(runtime.db,chaos_target_chat_id=int(d.split(':')[-1]),mad_waiting=False);bot.send_message(c.message.chat.id,'🎯 تم اختيار الكروب.',reply_markup=menu());return
   t=target(runtime.db)
   if not t:return bot.send_message(c.message.chat.id,'🎯 اختار كروبًا أولًا.')
   msgs=runtime.db.recent_messages(t,120)
   if d=='mad:send':save(runtime.db,mad_waiting='send');return bot.send_message(c.message.chat.id,'📨 أرسل الرسالة/الصورة/الفيديو الآن.')
   if d=='mad:random' and msgs:bot.copy_message(t,t,random.choice(msgs).message_id)
   elif d=='mad:remix':bot.send_message(t,' '.join(random.sample(toks(msgs),min(10,len(toks(msgs))))) if toks(msgs) else '3:')
   elif d=='mad:tip':bot.send_message(t,f'⭐ Tip: {random.randint(1,1000)}')
   elif d=='mad:mood':bot.send_message(t,random.choice(['3:','المود اليوم غريب شوية','صافي خليوها على الله']))
   elif d=='mad:media':
    media=[m for m in msgs if getattr(m,'media_type',None)]
    if media:bot.copy_message(t,t,random.choice(media).message_id)
    else:return bot.send_message(c.message.chat.id,'🖼️ لا توجد وسائط محفوظة.')
   elif d=='mad:poll':
    words=list(dict.fromkeys(toks(msgs)))
    if len(words)>=3:bot.send_poll(t,'شنو كلمة اليوم؟',random.sample(words,min(8,len(words))),is_anonymous=True)
    else:return bot.send_message(c.message.chat.id,'🗳️ الكلمات غير كافية.')
   elif d=='mad:status':bot.send_message(c.message.chat.id,f'🧪 الحالة\n🎯 {t}\n💬 {len(msgs)} رسالة',reply_markup=menu());return
   elif d=='mad:disable':save(runtime.db,chaos_target_chat_id=None,mad_waiting=False);bot.send_message(c.message.chat.id,'🛑 تم إيقاف المختبر.',reply_markup=menu());return
   try:bot.answer_callback_query(c.id,'تم التنفيذ ✅')
   except:pass
  except Exception:
   logging.getLogger(__name__).exception('Merva Lab callback failed: %s',d);bot.send_message(c.message.chat.id,'❌ Merva Lab error. Check Render logs.')
 @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
 def lab_input(m):
  mode=state(runtime.db).get('mad_waiting');t=target(runtime.db)
  if mode=='addchat':
   if getattr(m,'forward_from_chat',None):save(runtime.db,chaos_target_chat_id=m.forward_from_chat.id,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم اختيار الكروب.',reply_markup=menu());return
   if getattr(m,'content_type','')=='text':
    try:cid=int(m.text.strip());save(runtime.db,chaos_target_chat_id=cid,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم اختيار الكروب.',reply_markup=menu());return
    except:pass
   return bot.send_message(m.chat.id,'❌ أرسل Forward من الكروب أو chat ID.')
  if not t:return bot.send_message(m.chat.id,'🎯 اختار كروبًا أولًا')
  try:bot.copy_message(t,m.chat.id,m.message_id);save(runtime.db,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم الإرسال.')
  except Exception as e:bot.send_message(m.chat.id,'❌ '+str(e)[:120])
