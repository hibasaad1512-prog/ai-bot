from __future__ import annotations
import json, random, re, logging
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
def groups(db):
 from sqlalchemy import text
 with db.engine.connect() as c:rows=c.execute(text('SELECT chat_id,COUNT(*) messages FROM chat_messages WHERE chat_id<0 GROUP BY chat_id ORDER BY MAX(timestamp) DESC LIMIT 200')).mappings().all()
 return [{'chat_id':int(x['chat_id']),'messages':int(x['messages'])} for x in rows]
def toks(msgs):
 out=[]
 for m in msgs:out+=re.findall(r'[^\s]{1,24}',getattr(m,'text','') or '')
 return [x for x in out if not x.startswith(('/', 'http://','https://'))]
def menu():
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=2)
 items=[('🎯 اختيار الكروب','mad:chats'),('➕ تعريف كروب','mad:addchat'),('📨 إرسال','mad:send'),('🎲 عشوائي','mad:random'),('🧪 خلط','mad:remix'),('🗳️ استطلاع عشوائي','mad:poll'),('💳 Payment','mad:payment'),('🎭 مود','mad:mood'),('🖼️ وسائط عشوائية','mad:media'),('📊 الحالة','mad:status'),('⚙️ Auto Send','mad:auto'),('🔥 Auto+','mad:autoplus'),('⚙️ تخصيص العشوائية','mad:custom')]
 for a,b in items:k.add(types.InlineKeyboardButton(a,callback_data=b))
 k.add(types.InlineKeyboardButton('🚪 خروج من المختبر',callback_data='mad:exit'));return k
def group_menu(gs):
 from telebot import types
 k=types.InlineKeyboardMarkup(row_width=1)
 if not gs:k.add(types.InlineKeyboardButton('⚠️ لا توجد كروبات محفوظة',callback_data='mad:addchat'))
 for g in gs:k.add(types.InlineKeyboardButton(f"🎯 {g['chat_id']} · {g['messages']} رسالة",callback_data=f"mad:select:{g['chat_id']}"))
 k.add(types.InlineKeyboardButton('⬅️ رجوع',callback_data='mad:open'));return k
def register(bot,runtime):
 @bot.message_handler(commands=['admin'])
 def admin(m):
  if owner(m):bot.send_message(m.chat.id,'🔐 GOD PANEL\n\n🧪 مختبر الميرفاوية',reply_markup=menu())
 @bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('mad:'))
 def cb(c):
  if not owner_id(c):
   try:bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
   except:pass
   return
  d=c.data
  try:
   try:bot.answer_callback_query(c.id)
   except:pass
   chat_id=c.message.chat.id
   if d=='mad:exit':save(runtime.db,mad_waiting=False);bot.send_message(chat_id,'🚪 خرجت من المختبر. Auto Send مازال مستمرًا إذا كان مفعّلًا.');return
   if d=='mad:open':bot.send_message(chat_id,'🧪 مختبر الميرفاوية',reply_markup=menu());return
   if d=='mad:chats':bot.send_message(chat_id,'🎯 اختر الكروب:',reply_markup=group_menu(groups(runtime.db)));return
   if d=='mad:addchat':save(runtime.db,mad_waiting='addchat');bot.send_message(chat_id,'➕ أرسل Forward من الكروب أو chat ID.');return
   if d.startswith('mad:select:'):save(runtime.db,chaos_target_chat_id=int(d.split(':')[-1]),mad_waiting=False);bot.send_message(chat_id,'🎯 تم اختيار الكروب.',reply_markup=menu());return
   if d=='mad:auto':
    enabled=not bool(state(runtime.db).get('mad_auto'));save(runtime.db,mad_auto=enabled);bot.send_message(chat_id,('🤖 Auto Send: ON\n💾 محفوظ في Neon ويستأنف بعد Restart.' if enabled else '🛑 Auto Send: OFF'),reply_markup=menu());return
   if d=='mad:autoplus':
    enabled=not bool(state(runtime.db).get('mad_autoplus'));save(runtime.db,mad_autoplus=enabled,mad_auto=enabled);bot.send_message(chat_id,('🔥 Auto+ ON\n🎲 AI/عشوائي/وسائط بشكل متنوع\n💾 محفوظ في Neon.' if enabled else '🛑 Auto+ OFF'),reply_markup=menu());return
   if d=='mad:custom':
    mode=state(runtime.db).get('mad_mode','mix');modes={'mix':'🎲 MIX: عشوائي + AI','random':'🎲 RANDOM: عشوائي فقط','ai':'🤖 AI: AI فقط'};new={'mix':'random','random':'ai','ai':'mix'}[mode];save(runtime.db,mad_mode=new);bot.send_message(chat_id,'⚙️ وضع الرد: '+modes[new],reply_markup=menu());return
   t=target(runtime.db)
   if not t:return bot.send_message(chat_id,'🎯 اختار كروبًا أولًا.')
   msgs=runtime.db.recent_messages(t,500);words=toks(msgs)
   if d=='mad:send':save(runtime.db,mad_waiting='send');return bot.send_message(chat_id,'📨 أرسل الآن أي محتوى: نص، صورة، فيديو، Sticker، GIF أو ملف.')
   if d=='mad:random' and msgs:bot.copy_message(t,t,random.choice(msgs).message_id)
   elif d=='mad:remix':
    n=random.randint(3,min(15,len(words))) if words else 0;bot.send_message(t,' '.join(random.sample(words,n)) if n else '3:')
   elif d=='mad:payment':
    from telebot import types
    amount=random.randint(5,1000);pool=words or ['Merva','اختيار','اليوم','شيء','عشوائي'];title=' '.join(random.sample(pool,min(random.randint(1,3),len(pool))))[:32];description=' '.join(random.sample(pool,min(random.randint(2,6),len(pool))))[:255];k=types.InlineKeyboardMarkup();k.add(types.InlineKeyboardButton(f'⭐ {amount} Stars',callback_data=f'mad:pay:{amount}'));bot.send_message(t,random.choice(['✨ اختيار عشوائي','🎁 افتح الاختيار','🪙 خيار اليوم','🎟️ جرّب هذا الاختيار']),reply_markup=k);save(runtime.db,mad_pending_payment={'chat_id':t,'amount':amount,'title':title,'description':description})
   elif d.startswith('mad:pay:'):
    from telebot import types
    amount=max(5,min(100000,int(d.split(':')[-1])));pool=words or ['Merva','اختيار','اليوم','شيء','عشوائي'];title=' '.join(random.sample(pool,min(random.randint(1,3),len(pool))))[:32];description=' '.join(random.sample(pool,min(random.randint(2,6),len(pool))))[:255];bot.send_invoice(t,title,description,f'merva_item_{amount}','XTR',[types.LabeledPrice(title,amount)])
   elif d=='mad:mood':bot.send_message(t,random.choice(['3:','المود اليوم غريب شوية','صافي خليوها على الله','سلام لاباس؟ صافي مزيان','واش؟','مزيان هادي']))
   elif d=='mad:media':
    media=[m for m in msgs if getattr(m,'media_type',None)]
    if media:bot.copy_message(t,t,random.choice(media).message_id)
    else:return bot.send_message(chat_id,'🖼️ لا توجد وسائط محفوظة.')
   elif d=='mad:poll':
    pool=list(dict.fromkeys(words));random.shuffle(pool);n=random.randint(3,min(10,len(pool))) if len(pool)>=3 else 0
    if n:
     options=random.sample(pool,n);question=' '.join(random.sample(pool,min(random.randint(1,4),len(pool))));bot.send_poll(t,question,options,is_anonymous=True)
    else:return bot.send_message(chat_id,'🗳️ الكلمات غير كافية.')
   elif d=='mad:status':bot.send_message(chat_id,f'🧪 الحالة\n🎯 {t}\n💬 {len(msgs)} رسالة\n🎲 Mode: {state(runtime.db).get("mad_mode","mix")}\n🤖 Auto: {"ON" if state(runtime.db).get("mad_auto") else "OFF"}',reply_markup=menu());return
   else:return bot.send_message(chat_id,'⚠️ الأمر غير معروف.',reply_markup=menu())
  except Exception as exc:
   logging.getLogger(__name__).exception('Merva Lab callback failed: %s',d)
   try:bot.send_message(ADMIN_ID,f'❌ Merva Lab error: {type(exc).__name__}: {str(exc)[:500]}')
   except:pass
 @bot.pre_checkout_query_handler(func=lambda q:bool(getattr(q,'invoice_payload','')) and str(q.invoice_payload).startswith('merva_item_'))
 def merva_precheckout(q):
  try:bot.answer_pre_checkout_query(q.id,ok=True)
  except Exception:logging.getLogger(__name__).exception('Merva Stars pre-checkout failed')
 @bot.message_handler(content_types=['successful_payment'])
 def merva_payment_received(m):
  p=getattr(m,'successful_payment',None)
  if not p:return
  try:save(runtime.db,last_stars_payment={'chat_id':m.chat.id,'user_id':m.from_user.id,'amount':p.total_amount,'payload':p.invoice_payload,'charge_id':p.telegram_payment_charge_id})
  except Exception:logging.getLogger(__name__).exception('Merva Stars payment persistence failed')
 @bot.message_handler(content_types=['text','photo','video','sticker','animation','document','audio','voice','video_note'],func=lambda m:owner(m) and bool(state(runtime.db).get('mad_waiting')))
 def lab_input(m):
  mode=state(runtime.db).get('mad_waiting');t=target(runtime.db)
  if mode=='addchat':
   if getattr(m,'forward_from_chat',None):
    cid=m.forward_from_chat.id;s=state(runtime.db);known=[x for x in s.get('known_chats',[]) if int(x.get('chat_id',0))!=int(cid)];known.insert(0,{'chat_id':cid,'title':getattr(m.forward_from_chat,'title',None),'username':getattr(m.forward_from_chat,'username',None)});save(runtime.db,known_chats=known[:100],chaos_target_chat_id=cid,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم اختيار الكروب.',reply_markup=menu());return
   if getattr(m,'content_type','')=='text':
    try:cid=int(m.text.strip());save(runtime.db,chaos_target_chat_id=cid,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم اختيار الكروب.',reply_markup=menu());return
    except:pass
   return bot.send_message(m.chat.id,'❌ أرسل Forward من الكروب أو chat ID.')
  if mode=='send':
   if not t:return bot.send_message(m.chat.id,'🎯 اختار كروبًا أولًا')
   try:bot.copy_message(t,m.chat.id,m.message_id);save(runtime.db,mad_waiting=False);bot.send_message(m.chat.id,'✅ تم إرسال المحتوى إلى الكروب.')
   except Exception as e:bot.send_message(m.chat.id,'❌ فشل الإرسال: '+str(e)[:160]);save(runtime.db,mad_waiting=False)
