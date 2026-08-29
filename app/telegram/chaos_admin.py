from __future__ import annotations
import json,random,re
from app.config import settings
ADMIN_ID=8734853156

def owner(m):
 u=getattr(m,'from_user',None);c=getattr(m,'chat',None)
 return bool(u and c and c.type=='private' and u.id==ADMIN_ID)
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
 with db.engine.connect() as c:r=c.execute(text('SELECT chat_id,COUNT(*) messages FROM chat_messages WHERE chat_id<0 GROUP BY chat_id ORDER BY MAX(timestamp) DESC LIMIT 40')).mappings().all()
 return [dict(x) for x in r]
def toks(msgs):
 out=[]
 for m in msgs:out+=re.findall(r'[^\s]{2,24}',getattr(m,'text','') or '')
 return [x for x in out if not x.startswith(('/', 'http://','https://'))]
def mix(msgs):
 w=toks(msgs)
 if not w:return '3:'
 random.shuffle(w);return ' '.join(w[:random.randint(4,12)])
def menu():
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=2)
 for a,b in [('🎯 Choose chat','mad:chats'),('📨 Send anything','mad:send'),('⚡ Random','mad:random'),('🧪 Remix','mad:remix'),('🗳 Poll','mad:poll'),('⭐ Tip','mad:tip'),('🎭 Mood','mad:mood'),('📊 Status','mad:status')]:k.add(types.InlineKeyboardButton(a,callback_data=b))
 k.add(types.InlineKeyboardButton('🛑 Disable','mad:disable'));return k
def group_menu(gs):
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=1)
 for g in gs:k.add(types.InlineKeyboardButton(f"🎯 {g['chat_id']} · {g['messages']} msgs",callback_data=f"mad:select:{g['chat_id']}"))
 k.add(types.InlineKeyboardButton('⬅️ Back',callback_data='mad:menu'));return k
def register(bot,runtime):
 @bot.message_handler(commands=['mad','madadmin','chaosadmin'])
 def mad(m):
  if owner(m):bot.send_message(m.chat.id,'🧪 MERVA LAB\n\n🎯 اختار كروب ومن بعد random / remix / poll / tip / media / mood.',reply_markup=menu())
 @bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('mad:'))
 def cb(c):
  if getattr(c,'from_user',None).id!=ADMIN_ID or getattr(c.message.chat,'type',None)!='private':return bot.answer_callback_query(c.id,'not authorized',show_alert=True)
  d=c.data;t=target(runtime.db)
  if d=='mad:menu':bot.edit_message_text('🧪 MERVA LAB',c.message.chat.id,c.message.message_id,reply_markup=menu());return
  if d=='mad:chats':bot.edit_message_text('🎯 اختار الكروب:',c.message.chat.id,c.message.message_id,reply_markup=group_menu(groups(runtime.db)));return
  if d.startswith('mad:select:'):save(runtime.db,chaos_target_chat_id=int(d.split(':')[-1]),mad_waiting=False);bot.edit_message_text('🎯 Selected. Actions غادي يخدمو هنا.',c.message.chat.id,c.message.message_id,reply_markup=menu());return
  if not t:return bot.answer_callback_query(c.id,'اختار كروب أولاً',show_alert=True)
  msgs=runtime.db.recent_messages(t,120)
  try:
   if d=='mad:send':save(runtime.db,mad_waiting=True);bot.send_message(c.message.chat.id,'📨 صيفط دابا أي حاجة: نص، صورة، فيديو، sticker، GIF، voice، document...');return
   if d=='mad:random':bot.copy_message(t,t,random.choice(msgs).message_id)
   elif d=='mad:remix':bot.send_message(t,mix(msgs))
   elif d=='mad:tip':bot.send_message(t,mix(msgs)+f'\n\n⭐ tip: {random.randint(1,1000)} stars')
   elif d=='mad:poll':
    o=random.sample(toks(msgs),min(8,len(toks(msgs))))
    if len(o)<3:return bot.answer_callback_query(c.id,'كلمات غير كافية',show_alert=True)
    bot.send_poll(t,random.choice(['شنو كلمة اليوم؟','شنو الأكثر تكراراً؟']),o,is_anonymous=True)
   elif d=='mad:mood':bot.send_message(t,random.choice(['3:','المود اليوم غريب شوية','كنراقب فقط 👀','صافي خليوها على الله','واش هادشي قانوني أصلا؟']))
   elif d=='mad:status':bot.edit_message_text(f'🧪 STATUS\n\n🎯 Target: {t}\n💬 Groups: {len(groups(runtime.db))}\n⭐ Tip: 1–1000\n📨 Any media: enabled',c.message.chat.id,c.message.message_id,reply_markup=menu());return
   elif d=='mad:disable':save(runtime.db,chaos_target_chat_id=None,mad_waiting=False);bot.edit_message_text('🛑 Lab disabled.',c.message.chat.id,c.message.message_id,reply_markup=menu());return
   bot.answer_callback_query(c.id,'done ✅')
  except Exception as e:bot.answer_callback_query(c.id,f'failed: {str(e)[:40]}',show_alert=True)
 @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
 def any_media(m):
  t=target(runtime.db)
  if t:
   try:bot.copy_message(t,m.chat.id,m.message_id);bot.send_message(m.chat.id,'تم الإرسال للكروب المحدد ✅')
   except Exception:bot.send_message(m.chat.id,'ماقدرتش ننسخ هاد النوع ❌')
  save(runtime.db,mad_waiting=False)
