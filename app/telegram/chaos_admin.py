from __future__ import annotations
import json, random, logging
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
  logging.getLogger(__name__).warning('admin edit failed: %s',exc); return False
 except Exception as exc:
  logging.getLogger(__name__).warning('admin edit failed: %s',exc); return False

def groups(db,bot=None):
 from sqlalchemy import text
 by_id={}
 try:
  with db.engine.connect() as c:
   rows=c.execute(text('SELECT chat_id,COUNT(*) messages,MAX(timestamp) last_seen FROM chat_messages WHERE chat_id<0 GROUP BY chat_id ORDER BY last_seen DESC LIMIT 100')).mappings().all()
   for x in rows: by_id[int(x['chat_id'])]=dict(x)
 except Exception: pass
 known={int(x.get('chat_id')):x for x in state(db).get('known_chats',[]) if str(x.get('chat_id','')).lstrip('-').isdigit()}
 for cid,x in known.items(): by_id.setdefault(cid,{'chat_id':cid,'messages':0})
 result=[]
 for cid,x in by_id.items():
  title=known.get(cid,{}).get('title') or known.get(cid,{}).get('username') or str(cid)
  if bot:
   try:
    ch=bot.get_chat(cid); title=getattr(ch,'title',None) or getattr(ch,'username',None) or title
   except Exception: pass
  result.append({'chat_id':cid,'messages':int(x.get('messages',0)),'title':title})
 return sorted(result,key=lambda x:x['messages'],reverse=True)[:100]

def menu():
 return InlineKeyboardMarkup([
  [InlineKeyboardButton('🎯 الكروبات',callback_data='mad:chats'),InlineKeyboardButton('🔄 تحديث',callback_data='mad:refresh')],
  [InlineKeyboardButton('🤖 AI & APIs',callback_data='mad:ai'),InlineKeyboardButton('🧪 المختبر',callback_data='mad:lab')],
  [InlineKeyboardButton('🎲 العشوائية',callback_data='mad:random_menu'),InlineKeyboardButton('🛠 أدوات',callback_data='mad:tools')],
  [InlineKeyboardButton('📊 الحالة',callback_data='mad:status')]
 ])
def back(to='mad:home'): return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ رجوع',callback_data=to)]])
def group_menu(gs):
 rows=[[InlineKeyboardButton(f"🎯 {str(g['title'])[:45]}",callback_data=f"mad:select:{g['chat_id']}")] for g in gs]
 rows += [[InlineKeyboardButton('🔄 تحديث',callback_data='mad:refresh')],[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]]
 return InlineKeyboardMarkup(rows)
def sub_menu(kind):
 if kind=='ai': rows=[[InlineKeyboardButton('🔑 إدارة المفاتيح',callback_data='mad:keys')],[InlineKeyboardButton('🩺 فحص APIs',callback_data='mad:api_test')]]
 elif kind=='random': rows=[[InlineKeyboardButton('🎲 إرسال عشوائي الآن',callback_data='mad:random')],[InlineKeyboardButton('🖼️ وسائط عشوائية',callback_data='mad:media')]]
 elif kind=='tools': rows=[[InlineKeyboardButton('🗑️ حذف رسالة',callback_data='mad:delete_menu')],[InlineKeyboardButton('🚪 مغادرة الكروب',callback_data='mad:leave')],[InlineKeyboardButton('📨 إرسال',callback_data='mad:send')]]
 else: rows=[]
 rows.append([InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]); return InlineKeyboardMarkup(rows)

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
  d=c.data;cid=c.message.chat.id
  try:bot.answer_callback_query(c.id)
  except:pass
  try:
   if d in ('mad:home','mad:open'):
    _safe_edit(bot,cid,c.message.message_id,'🔐 GOD PANEL\n\n🎯 اختر قسمًا:',menu());return
   if d in ('mad:chats','mad:refresh'):
    _safe_edit(bot,cid,c.message.message_id,'🎯 <b>الكروبات</b>\n\nهذه هي الكروبات التي يعرفها البوت حاليًا.',group_menu(groups(runtime.db,bot)));return
   if d.startswith('mad:select:'):
    target_id=int(d.split(':')[-1]);save(runtime.db,chaos_target_chat_id=target_id,mad_waiting=False);_safe_edit(bot,cid,c.message.message_id,f'🎯 <b>الكروب الرئيسي</b>\n\n{target_id}\n\nتم التحديد.',menu());return
   if d in ('mad:ai','mad:random_menu','mad:tools'):
    title={'mad:ai':'🤖 AI & APIs','mad:random_menu':'🎲 العشوائية','mad:tools':'🛠 الأدوات'}[d];kind={'mad:ai':'ai','mad:random_menu':'random','mad:tools':'tools'}[d];_safe_edit(bot,cid,c.message.message_id,title,sub_menu(kind));return
   if d=='mad:lab':
    _safe_edit(bot,cid,c.message.message_id,'🧪 <b>المختبر</b>\n\nيعمل على الكروب الرئيسي فقط.',sub_menu('tools'));return
   if d=='mad:status':
    t=target(runtime.db);s=state(runtime.db);_safe_edit(bot,cid,c.message.message_id,f'📊 <b>الحالة</b>\n\n🎯 Current: {t or "غير محدد"}\n🎲 Random: {s.get("mad_mode","mix")}',back());return
   t=target(runtime.db)
   if d in ('mad:random','mad:media','mad:send','mad:delete_menu','mad:leave') and not t:
    _safe_edit(bot,cid,c.message.message_id,'🎯 اختر الكروب الرئيسي أولًا.',InlineKeyboardMarkup([[InlineKeyboardButton('🎯 اختيار الكروب',callback_data='mad:chats')],[InlineKeyboardButton('⬅️ رجوع',callback_data='mad:home')]]));return
   msgs=runtime.db.recent_messages(t,200)
   if d=='mad:random' and msgs: bot.copy_message(t,t,random.choice(msgs).message_id);return
   if d=='mad:media':
    media=[m for m in msgs if getattr(m,'media_type',None)]
    if media:bot.copy_message(t,t,random.choice(media).message_id)
    return
   if d=='mad:send': save(runtime.db,mad_waiting='send');_safe_edit(bot,cid,c.message.message_id,'📨 أرسل المحتوى الآن.',back());return
   if d=='mad:delete_menu':
    buttons=[[InlineKeyboardButton(f'🗑️ {(getattr(m,"text",None) or getattr(m,"caption",None) or "رسالة")[:45]}',callback_data=f'mad:delete:{m.message_id}')] for m in msgs[-15:][::-1]];buttons.append([InlineKeyboardButton('⬅️ رجوع',callback_data='mad:tools')]);_safe_edit(bot,cid,c.message.message_id,'🗑️ اختر الرسالة:',InlineKeyboardMarkup(buttons));return
   if d.startswith('mad:delete:'):
    bot.delete_message(t,int(d.split(':')[-1]));_safe_edit(bot,cid,c.message.message_id,'✅ تم الحذف.',sub_menu('tools'));return
   if d=='mad:leave':
    bot.leave_chat(t);save(runtime.db,chaos_target_chat_id=None);_safe_edit(bot,cid,c.message.message_id,'🚪 غادرت الكروب.',menu());return
   if d in ('mad:keys','mad:api_test'):
    _safe_edit(bot,cid,c.message.message_id,'🤖 <b>AI & APIs</b>\n\n🔐 المفاتيح مخفية بالكامل.\n🩺 الاختبار يعرض حالة الاتصال فقط.',back('mad:ai'));return
  except Exception as exc:
   logging.getLogger(__name__).exception('Merva Lab callback failed: %s',d)
   try:bot.send_message(ADMIN_ID,f'❌ Merva Lab error: {type(exc).__name__}: {str(exc)[:300]}')
   except:pass
 @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
 def lab_input(m):
  if state(runtime.db).get('mad_waiting')=='send' and target(runtime.db):
   try:bot.copy_message(target(runtime.db),m.chat.id,m.message_id);save(runtime.db,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم الإرسال.',reply_markup=menu())
   except Exception as e:bot.send_message(m.chat.id,'❌ فشل الإرسال: '+str(e)[:120]);save(runtime.db,mad_waiting=False)
