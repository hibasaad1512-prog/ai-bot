from __future__ import annotations
import json, random, re
from app.config import settings
ADMIN_ID = 8734853156


def owner(m):
    u = getattr(m, 'from_user', None); c = getattr(m, 'chat', None)
    return bool(u and c and c.type == 'private' and u.id == ADMIN_ID)


def state(db):
    from sqlalchemy import text
    with db.engine.connect() as c:
        r = c.execute(text('SELECT state_json FROM chat_state WHERE chat_id=:id'), {'id': ADMIN_ID}).mappings().first()
    try: return json.loads(r['state_json']) if r else {}
    except Exception: return {}


def save(db, **kw):
    s = state(db); s.update(kw); db.save_state(ADMIN_ID, s)


def target(db):
    try: return int(state(db).get('chaos_target_chat_id'))
    except Exception: return None


def groups(db):
    """Merge DB-observed chats with chats explicitly registered by the owner."""
    from sqlalchemy import text
    with db.engine.connect() as c:
        rows = c.execute(text('''SELECT chat_id, COUNT(*) AS messages, MAX(timestamp) AS last_seen
            FROM chat_messages WHERE chat_id < 0 GROUP BY chat_id ORDER BY MAX(timestamp) DESC LIMIT 200''')).mappings().all()
    merged = {int(x['chat_id']): {'chat_id': int(x['chat_id']), 'messages': int(x['messages']), 'title': None, 'username': None}
              for x in rows}
    for x in state(db).get('known_chats', []):
        try:
            cid = int(x['chat_id'])
            merged[cid] = {**merged.get(cid, {'chat_id': cid, 'messages': 0}), **x, 'chat_id': cid}
        except Exception:
            pass
    return sorted(merged.values(), key=lambda x: x.get('title') or x.get('username') or str(x['chat_id']))[:100]


def remember_chat(db, chat):
    known = state(db).get('known_chats', [])
    cid = int(chat.id)
    item = {'chat_id': cid, 'title': getattr(chat, 'title', None), 'username': getattr(chat, 'username', None), 'type': getattr(chat, 'type', None)}
    known = [x for x in known if int(x.get('chat_id', 0)) != cid]
    known.insert(0, item)
    save(db, known_chats=known[:100])
    return item


def resolve_text(bot, value):
    """Resolve @username, public t.me links, or -100... chat ids."""
    value = (value or '').strip()
    if value.startswith('@'):
        return bot.get_chat(value)
    m = re.search(r't\.me/(?:c/)?([A-Za-z0-9_+\-]+)', value)
    if not m:
        try: return bot.get_chat(int(value))
        except Exception: return None
    token = m.group(1)
    if token.startswith('c/'):
        token = token[2:]
    if token.isdigit():
        return bot.get_chat(int('-100' + token))
    if not token.startswith('+'):
        return bot.get_chat('@' + token)
    return None


def toks(msgs):
    out = []
    for m in msgs:
        out += re.findall(r'[^\s]{2,24}', getattr(m, 'text', '') or '')
    return [x for x in out if not x.startswith(('/', 'http://', 'https://'))]


def mix(msgs):
    w = toks(msgs)
    if not w: return '3:'
    random.shuffle(w)
    return ' '.join(w[:random.randint(4, 12)])


def menu():
    from telebot import types
    k = types.InlineKeyboardMarkup(row_width=2)
    for a, b in [
        ('🎯 اختيار الكروب', 'mad:chats'), ('➕ إضافة/تعريف كروب', 'mad:addchat'),
        ('📨 إرسال أي شيء', 'mad:send'), ('🎲 عشوائي', 'mad:random'),
        ('🧪 خلط كلمات الشات', 'mad:remix'), ('🗳️ استطلاع عشوائي', 'mad:poll'),
        ('⭐ Tip عشوائي', 'mad:tip'), ('🎭 رسالة / مود', 'mad:mood'),
        ('🖼️ وسائط الكروب', 'mad:media'), ('📊 الحالة', 'mad:status'),
    ]: k.add(types.InlineKeyboardButton(a, callback_data=b))
    k.add(types.InlineKeyboardButton('⬅️ لوحة التحكم الرئيسية', callback_data='mad:god'))
    k.add(types.InlineKeyboardButton('🛑 إيقاف المختبر', callback_data='mad:disable'))
    return k


def group_menu(gs):
    from telebot import types
    k = types.InlineKeyboardMarkup(row_width=1)
    if not gs:
        k.add(types.InlineKeyboardButton('⚠️ لا توجد كروبات معروفة بعد', callback_data='mad:addchat'))
    for g in gs:
        label = g.get('title') or (('@' + g['username']) if g.get('username') else str(g['chat_id']))
        k.add(types.InlineKeyboardButton(f"🎯 {label} · {g.get('messages', 0)} رسالة", callback_data=f"mad:select:{g['chat_id']}"))
    k.add(types.InlineKeyboardButton('➕ إضافة/تعريف كروب', callback_data='mad:addchat'))
    k.add(types.InlineKeyboardButton('🔄 تحديث القائمة', callback_data='mad:chats'))
    k.add(types.InlineKeyboardButton('⬅️ رجوع', callback_data='mad:open'))
    return k


def register(bot, runtime):
    # Telegram does not provide a "list all chats the bot belongs to" API.
    # The reliable non-AI solution is to register chat metadata from every
    # incoming update before normal handlers run. This means a group appears
    # in the Lab as soon as the bot receives ANY update from it, even when no
    # AI response was generated and no message was stored yet.
    if not getattr(bot, '_merva_chat_discovery_wrapped', False):
        original_process = bot.process_new_updates

        def process_with_discovery(updates):
            try:
                for update in updates or []:
                    msg = (
                        getattr(update, 'message', None)
                        or getattr(update, 'edited_message', None)
                        or getattr(update, 'channel_post', None)
                        or getattr(update, 'edited_channel_post', None)
                    )
                    chat = getattr(msg, 'chat', None)
                    if chat and getattr(chat, 'type', None) in ('group', 'supergroup'):
                        remember_chat(runtime.db, chat)
            except Exception:
                pass
            return original_process(updates)

        bot.process_new_updates = process_with_discovery
        bot._merva_chat_discovery_wrapped = True

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('mad:'))
    def cb(c):
        if getattr(c, 'from_user', None).id != ADMIN_ID or getattr(c.message.chat, 'type', None) != 'private':
            return bot.answer_callback_query(c.id, 'غير مصرح', show_alert=True)
        d = c.data; t = target(runtime.db)
        if d == 'mad:open':
            bot.edit_message_text('🧪 مختبر الميرفاوية\n\nاختر كروبًا ثم استخدم الإرسال المباشر أو الأدوات العشوائية. أدوات الإرسال/الوسائط لا تمر عبر AI.', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
        if d == 'mad:god':
            from app.telegram.memory_admin import menu as god_menu
            bot.edit_message_text('🔐 لوحة التحكم الرئيسية', c.message.chat.id, c.message.message_id, reply_markup=god_menu()); return
        if d == 'mad:chats':
            bot.edit_message_text('🎯 اختر الكروب، أو استخدم «➕ إضافة/تعريف كروب» إذا لم يظهر:', c.message.chat.id, c.message.message_id, reply_markup=group_menu(groups(runtime.db))); return
        if d == 'mad:addchat':
            save(runtime.db, mad_waiting='addchat')
            bot.send_message(c.message.chat.id, '➕ تعريف كروب جديد\n\nأرسل واحدًا من التالي:\n• Forward لرسالة من الكروب (يعمل حتى للكروبات الخاصة)\n• @username للكروب العام\n• رابط t.me/... العام\n• chat ID مثل -1001234567890\n\nإذا كان الرابط دعوة خاصة مثل t.me/+...، أرسل Forward من الكروب بدل الرابط لأن الرابط وحده لا يكشف chat ID.')
            return
        if d.startswith('mad:select:'):
            selected = int(d.split(':')[-1]); save(runtime.db, chaos_target_chat_id=selected, mad_waiting=False)
            bot.edit_message_text(f'🎯 تم اختيار الكروب: {selected}\n\nاختر العملية:', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
        if d == 'mad:send':
            if not t: return bot.answer_callback_query(c.id, 'اختار كروبًا أولًا 🎯', show_alert=True)
            save(runtime.db, mad_waiting='send')
            bot.send_message(c.message.chat.id, '📨 وضع الإرسال المباشر\n\nأرسل الآن نصًا أو صورة أو فيديو أو Sticker أو GIF أو Voice أو ملف. سيتم نسخه للكروب المحدد بدون AI.')
            return
        if not t: return bot.answer_callback_query(c.id, 'اختار كروبًا أولًا 🎯', show_alert=True)
        try:
            msgs = runtime.db.recent_messages(t, 120)
            if d == 'mad:random':
                if not msgs: return bot.answer_callback_query(c.id, 'لا توجد رسائل محفوظة لهذا الكروب بعد.', show_alert=True)
                bot.copy_message(t, t, random.choice(msgs).message_id)
            elif d == 'mad:remix': bot.send_message(t, mix(msgs))
            elif d == 'mad:tip': bot.send_message(t, mix(msgs) + f'\n\n⭐ tip: {random.randint(1, 1000)} stars')
            elif d == 'mad:poll':
                words = list(dict.fromkeys(toks(msgs)))
                if len(words) < 3: return bot.answer_callback_query(c.id, 'الكلمات المحفوظة غير كافية لعمل استطلاع.', show_alert=True)
                bot.send_poll(t, random.choice(['شنو كلمة اليوم؟', 'شنو الأكثر تكرارًا؟', 'شنو المود؟']), random.sample(words, min(8, len(words))), is_anonymous=True)
            elif d == 'mad:mood': bot.send_message(t, random.choice(['3:', 'المود اليوم غريب شوية', 'كنراقب فقط 👀', 'صافي خليوها على الله', 'واش هادشي قانوني أصلا؟']))
            elif d == 'mad:media':
                media = [m for m in msgs if getattr(m, 'media_type', None)]
                if not media: return bot.answer_callback_query(c.id, 'ما كايناش وسائط محفوظة لهذا الكروب بعد.', show_alert=True)
                bot.copy_message(t, t, random.choice(media).message_id)
            elif d == 'mad:status':
                bot.edit_message_text(f'🧪 حالة المختبر\n\n🎯 الكروب: {t}\n💬 الكروبات المعروفة: {len(groups(runtime.db))}\n💾 الرسائل المستخدمة: {len(msgs)}\n🤖 AI للإرسال/الوسائط: لا\n⭐ Tip: 1–1000', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
            elif d == 'mad:disable':
                save(runtime.db, chaos_target_chat_id=None, mad_waiting=False)
                bot.edit_message_text('🛑 تم إيقاف المختبر وإلغاء الكروب المحدد.', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
            bot.answer_callback_query(c.id, 'تم التنفيذ ✅')
        except Exception as e: bot.answer_callback_query(c.id, f'تعذر التنفيذ: {str(e)[:50]}', show_alert=True)

    @bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'animation', 'document', 'audio', 'voice', 'video_note'], func=lambda m: owner(m) and bool(state(runtime.db).get('mad_waiting')))
    def lab_input(m):
        mode = state(runtime.db).get('mad_waiting')
        if mode == 'addchat':
            try:
                chat = getattr(m, 'forward_from_chat', None)
                if not chat:
                    origin = getattr(m, 'forward_origin', None)
                    chat = getattr(origin, 'chat', None)
                if not chat and getattr(m, 'content_type', '') == 'text':
                    chat = resolve_text(bot, m.text)
                if not chat or getattr(chat, 'type', '') not in ('group', 'supergroup'):
                    bot.send_message(m.chat.id, '❌ ما قدرتش نتعرف على الكروب. جرّب Forward لرسالة منه أو @username/رابط عام.')
                    return
                item = remember_chat(runtime.db, chat)
                bot.send_message(m.chat.id, f"✅ تم تعريف الكروب وحفظه\n\n🎯 {item.get('title') or item.get('username') or item['chat_id']}\n🆔 {item['chat_id']}\n\nيمكنك الآن اختياره من «اختيار الكروب».")
            except Exception as e: bot.send_message(m.chat.id, f'❌ تعذر تعريف الكروب: {str(e)[:120]}')
            save(runtime.db, mad_waiting=False); return
        t = target(runtime.db)
        if not t:
            bot.send_message(m.chat.id, 'اختار الكروب أولًا 🎯'); save(runtime.db, mad_waiting=False); return
        try:
            bot.copy_message(t, m.chat.id, m.message_id)
            bot.send_message(m.chat.id, '✅ تم الإرسال للكروب المحدد بدون AI.')
        except Exception:
            bot.send_message(m.chat.id, '❌ ماقدرتش ننسخ هاد النوع.')
        save(runtime.db, mad_waiting=False)
