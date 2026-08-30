from __future__ import annotations
import json, random, re, logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
ADMIN_ID=8734853156

def owner(m):
 u=getattr(m,'from_user',None); c=getattr(m,'chat',None); return bool(u and c and c.type=='private' and int(u.id)==ADMIN_ID)
def owner_id(value):
 u=getattr(value,'from_user',None); return bool(u and int(u.id)==ADMIN_ID)
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

def _safe_edit(bot,chat_id,message_id,text,reply_markup=None):
 try:
  bot.edit_message_text(text,chat_id,message_id,reply_markup=reply_markup)
  return True
 except BadRequest as exc:
  if 'message is not modified' in str(exc).lower(): return True
  logging.getLogger(__name__).warning('safe edit failed: %s',exc); return False
 except Exception as exc:
  logging.getLogger(__name__).warning('safe edit failed: %s',exc); return False

def groups(db,bot=None):
 from sqlalchemy import text
 rows=[]
 with db.engine.connect() as c:
  try: rows=c.execute(text('SELECT chat_id,COUNT(*) messages,MAX(timestamp) last_seen FROM chat_messages WHERE chat_id<0 GROUP BY chat_id ORDER BY last_seen DESC LIMIT 200')).mappings().all()
  except Exception: rows=[]
 known={int(x.get('chat_id')):x for x in state(db).get('known_chats',[]) if str(x.get('chat_id','')).lstrip('-').isdigit()}
 by_id={int(x['chat_id']):dict(x) for x in rows}
 try:
  with db.engine.connect() as c: extra=c.execute(text("SELECT chat_id,title,username FROM telegram_chats WHERE chat_id<0 ORDER BY last_seen DESC LIMIT 200")).mappings().all()
  for x in extra:
   cid=int(x['chat_id']);by_id.setdefault(cid,{'chat_id':cid,'messages':0,'last_seen':0});known.setdefault(cid,{}).update({k:x.get(k) for k in ('title','username') if x.get(k)})
 except Exception: pass
 result=[]
 for cid,x in by_id.items():
  item=known.get(cid,{})
  title=item.get('title') or item.get('username')
  if bot:
   try:
    ch=bot.get_chat(cid); title=getattr(ch,'title',None) or getattr(ch,'username',None) or title
   except Exception: pass
  result.append({'chat_id':cid,'messages':int(x.get('messages',0)),'title':title or 'Unnamed chat'})
 return sorted(result,key=lambda x:x['messages'],reverse=True)[:100]

def menu():
 return InlineKeyboardMarkup([
  [InlineKeyboardButton('🎯 الكروبات',callback_data='mad:chats'),InlineKeyboardButton('🔄 تحديث',callback_data='mad:refresh')],
  [InlineKeyboardButton('🤖 AI & APIs',callback_data='mad:ai'),InlineKeyboardButton('🧪 المختبر',callback_data='mad:lab')],
  [InlineKeyboardButton('🎲 العشوائية',callback_data='mad:random_menu'),InlineKeyboardButton('🛠 أدوات',callback_data='mad:tools')],
  [InlineKeyboardButton('📊 الحالة',callback_data='mad:status')]
 ])

def group_menu(gs):
 rows=[[InlineKeyboardButton(f"🎯 {str(g['title'])[:45]}",callback_data=f"mad:select:{g['chat_id']}")] for g in gs]
 rows += [[InlineKeyboardButton('🔄 تحديث',callback_data='mad:refresh')],[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]]
 return InlineKeyboardMarkup(rows)

def sub_menu(kind):
 if kind=='ai': rows=[[InlineKeyboardButton('🔑 المفاتيح',callback_data='mad:keys')],[InlineKeyboardButton('🩺 فحص APIs',callback_data='mad:api_test')]]
 elif kind=='random': rows=[[InlineKeyboardButton('🎲 إرسال عشوائي',callback_data='mad:random')],[InlineKeyboardButton('🖼️ وسائط عشوائية',callback_data='mad:media')],[InlineKeyboardButton('⚙️ إعدادات العشوائية',callback_data='mad:custom')]]
 elif kind=='tools': rows=[[InlineKeyboardButton('🗑️ حذف رسالة',callback_data='mad:delete_menu')],[InlineKeyboardButton('🚪 مغادرة الكروب',callback_data='mad:leave')],[InlineKeyboardButton('📨 إرسال',callback_data='mad:send')]]
 else: rows=[]
 rows.append([InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')])
 return InlineKeyboardMarkup(rows)

def register(bot,runtime):
 @bot.message_handler(commands=['admin'])
 def admin(m):
  if owner(m): bot.send_message(m.chat.id,'🔐 GOD PANEL\n\n🎯 اختر قسمًا:',reply_markup=menu())
 @bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('mad:'))
 def cb(c):
  if not owner_id(c):
   try:bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
   except:pass
   return
  d=c.data;chat_id=c.message.chat.id
  try:bot.answer_callback_query(c.id)
  except:pass
  try:
   if d in ('mad:home','mad:open'):
    _safe_edit(bot,chat_id,c.message.message_id,'🔐 GOD PANEL\n\n🎯 اختر قسمًا:',menu());return
   if d in ('mad:chats','mad:refresh'):
    _safe_edit(bot,chat_id,c.message.message_id,'🎯 <b>الكروبات الموجودة حاليًا</b>',group_menu(groups(runtime.db,bot)));return
   if d.startswith('mad:select:'):
    cid=int(d.split(':')[-1]);save(runtime.db,chaos_target_chat_id=cid,mad_waiting=False);_safe_edit(bot,chat_id,c.message.message_id,f'🎯 <b>الكروب الحالي:</b> {cid}\n\nتم التحديد.',menu());return
   if d in ('mad:ai','mad:random_menu','mad:tools'):
    title={'mad:ai':'🤖 AI & APIs','mad:random_menu':'🎲 العشوائية','mad:tools':'🛠 أدوات'}[d];_safe_edit(bot,chat_id,c.message.message_id,title,sub_menu({'mad:ai':'ai','mad:random_menu':'random','mad:tools':'tools'}[d]));return
   if d=='mad:lab':
    _safe_edit(bot,chat_id,c.message.message_id,'🧪 <b>المختبر</b>\n\n🎯 الكروب الحالي فقط',sub_menu('tools'));return
   if d=='mad:status':
    t=target(runtime.db);s=state(runtime.db);_safe_edit(bot,chat_id,c.message.message_id,f'📊 <b>الحالة</b>\n\n🎯 Current: {t or "غير محدد"}\n🎲 Mode: {s.get("mad_mode","mix")}\n🤖 Auto: {"ON" if s.get("mad_auto") else "OFF"}',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]]));return
   t=target(runtime.db)
   if d in ('mad:random','mad:media','mad:send','mad:delete_menu','mad:leave','mad:custom') and not t:
    _safe_edit(bot,chat_id,c.message.message_id,'🎯 اختر الكروب أولًا.',InlineKeyboardMarkup([[InlineKeyboardButton('🎯 اختيار الكروب',callback_data='mad:chats')],[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]]));return
   msgs=runtime.db.recent_messages(t,500)
   if d=='mad:random' and msgs: bot.copy_message(t,t,random.choice(msgs).message_id);return
   if d=='mad:media':
    media=[m for m in msgs if getattr(m,'media_type',None)]
    if media:bot.copy_message(t,t,random.choice(media).message_id)
    return
   if d=='mad:send': save(runtime.db,mad_waiting='send');_safe_edit(bot,chat_id,c.message.message_id,'📨 أرسل المحتوى الآن.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ إلغاء',callback_data='mad:home')]]));return
   if d=='mad:delete_menu':
    buttons=[]
    for m in msgs[-15:][::-1]: buttons.append([InlineKeyboardButton(f'🗑️ {(getattr(m,"text",None) or getattr(m,"caption",None) or "رسالة")[:45]}',callback_data=f'mad:delete:{m.message_id}')])
    buttons.append([InlineKeyboardButton('⬅️ رجوع',callback_data='mad:tools')]);_safe_edit(bot,chat_id,c.message.message_id,'🗑️ اختر الرسالة:',InlineKeyboardMarkup(buttons));return
   if d.startswith('mad:delete:'):
    bot.delete_message(t,int(d.split(':')[-1]));_safe_edit(bot,chat_id,c.message.message_id,'✅ تم الحذف.',sub_menu('tools'));return
   if d=='mad:leave':
    bot.leave_chat(t);save(runtime.db,chaos_target_chat_id=None);_safe_edit(bot,chat_id,c.message.message_id,'🚪 غادرت الكروب.',menu());return
   if d=='mad:custom':
    mode=state(runtime.db).get('mad_mode','mix');new={'mix':'random','random':'ai','ai':'mix'}[mode];save(runtime.db,mad_mode=new);_safe_edit(bot,chat_id,c.message.message_id,f'🎲 Mode: {new}',sub_menu('random'));return
   if d in ('mad:keys','mad:api_test'):
    _safe_edit(bot,chat_id,c.message.message_id,'🤖 حالة الـAPI فقط — لا يتم عرض أي جزء من المفاتيح.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:ai')]]));return
  except Exception as exc:
   logging.getLogger(__name__).exception('Merva Lab callback failed: %s',d)
   try:bot.send_message(ADMIN_ID,f'❌ Merva Lab error: {type(exc).__name__}: {str(exc)[:300]}')
   except:pass
 @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
 def lab_input(m):
  if state(runtime.db).get('mad_waiting')=='send' and target(runtime.db):
   try:bot.copy_message(target(runtime.db),m.chat.id,m.message_id);save(runtime.db,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم الإرسال.',reply_markup=menu())
   except Exception as e:bot.send_message(m.chat.id,'❌ فشل الإرسال: '+str(e)[:120]);save(runtime.db,mad_waiting=False)
