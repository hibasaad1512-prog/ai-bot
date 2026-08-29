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
    from sqlalchemy import text
    with db.engine.connect() as c:
        r = c.execute(text('''
            SELECT chat_id, COUNT(*) AS messages
            FROM chat_messages
            WHERE chat_id < 0
            GROUP BY chat_id
            ORDER BY MAX(timestamp) DESC
            LIMIT 80
        ''' )).mappings().all()
    return [dict(x) for x in r]


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
    buttons = [
        ('🎯 اختيار الكروب', 'mad:chats'),
        ('📨 إرسال أي شيء', 'mad:send'),
        ('🎲 عشوائي', 'mad:random'),
        ('🧪 خلط كلمات الشات', 'mad:remix'),
        ('🗳️ استطلاع عشوائي', 'mad:poll'),
        ('⭐ Tip عشوائي', 'mad:tip'),
        ('🎭 رسالة / مود', 'mad:mood'),
        ('🖼️ وسائط الكروب', 'mad:media'),
        ('📊 الحالة', 'mad:status'),
    ]
    for a, b in buttons:
        k.add(types.InlineKeyboardButton(a, callback_data=b))
    k.add(types.InlineKeyboardButton('⬅️ لوحة التحكم الرئيسية', callback_data='mad:god'))
    k.add(types.InlineKeyboardButton('🛑 إيقاف المختبر', callback_data='mad:disable'))
    return k


def group_menu(gs):
    from telebot import types
    k = types.InlineKeyboardMarkup(row_width=1)
    if not gs:
        k.add(types.InlineKeyboardButton('⚠️ لا توجد كروبات محفوظة بعد', callback_data='mad:open'))
    for g in gs:
        k.add(types.InlineKeyboardButton(
            f"🎯 {g['chat_id']} · {g['messages']} رسالة محفوظة",
            callback_data=f"mad:select:{g['chat_id']}"
        ))
    k.add(types.InlineKeyboardButton('🔄 تحديث قائمة الكروبات', callback_data='mad:chats'))
    k.add(types.InlineKeyboardButton('⬅️ لوحة التحكم الرئيسية', callback_data='mad:god'))
    return k


def register(bot, runtime):
    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('mad:'))
    def cb(c):
        if getattr(c, 'from_user', None).id != ADMIN_ID or getattr(c.message.chat, 'type', None) != 'private':
            return bot.answer_callback_query(c.id, 'غير مصرح', show_alert=True)
        d = c.data; t = target(runtime.db)
        if d == 'mad:open':
            bot.edit_message_text(
                '🧪 مختبر الميرفاوية\n\n'
                'قسم التجارب والإرسال المباشر — هذه الأدوات لا تحتاج إلى الذكاء الاصطناعي إلا في الخلط الذكي للكلمات.\n\n'
                '🎯 اختر كروبًا أولًا، ثم استخدم أي أداة.',
                c.message.chat.id, c.message.message_id, reply_markup=menu())
            return
        if d == 'mad:god':
            from app.telegram.memory_admin import menu as god_menu
            bot.edit_message_text('🔐 لوحة التحكم الرئيسية\n\nكل أدوات الإدارة والتخصيص في مكان واحد.', c.message.chat.id, c.message.message_id, reply_markup=god_menu())
            return
        if d == 'mad:chats':
            bot.edit_message_text('🎯 اختر الكروب الذي تريد التحكم فيه:', c.message.chat.id, c.message.message_id, reply_markup=group_menu(groups(runtime.db)))
            return
        if d.startswith('mad:select:'):
            selected = int(d.split(':')[-1])
            save(runtime.db, chaos_target_chat_id=selected, mad_waiting=False)
            bot.edit_message_text(f'🎯 تم اختيار الكروب: {selected}\n\nالآن اختر العملية التي تريد تنفيذها:', c.message.chat.id, c.message.message_id, reply_markup=menu())
            return
        if d == 'mad:send':
            save(runtime.db, mad_waiting=True)
            bot.send_message(c.message.chat.id, '📨 **وضع الإرسال المباشر**\n\nأرسل الآن أي شيء من الخاص: نص، صورة، فيديو، Sticker، GIF، Voice أو ملف.\n\nسيتم نسخه إلى الكروب المحدد **بدون تمريره إلى الـAI**.')
            return
        if not t:
            return bot.answer_callback_query(c.id, 'اختار كروب أولًا 🎯', show_alert=True)
        try:
            msgs = runtime.db.recent_messages(t, 120)
            if d == 'mad:random':
                if not msgs: return bot.answer_callback_query(c.id, 'لا توجد رسائل محفوظة لهذا الكروب بعد.', show_alert=True)
                bot.copy_message(t, t, random.choice(msgs).message_id)
            elif d == 'mad:remix':
                bot.send_message(t, mix(msgs))
            elif d == 'mad:tip':
                bot.send_message(t, mix(msgs) + f'\n\n⭐ tip: {random.randint(1, 1000)} stars')
            elif d == 'mad:poll':
                words = list(dict.fromkeys(toks(msgs)))
                if len(words) < 3: return bot.answer_callback_query(c.id, 'الكلمات المحفوظة غير كافية لعمل استطلاع.', show_alert=True)
                bot.send_poll(t, random.choice(['شنو كلمة اليوم؟', 'شنو الأكثر تكرارًا؟', 'شنو المود؟']), random.sample(words, min(8, len(words))), is_anonymous=True)
            elif d == 'mad:mood':
                bot.send_message(t, random.choice(['3:', 'المود اليوم غريب شوية', 'كنراقب فقط 👀', 'صافي خليوها على الله', 'واش هادشي قانوني أصلا؟']))
            elif d == 'mad:media':
                media = [m for m in msgs if getattr(m, 'media_type', None)]
                if not media: return bot.answer_callback_query(c.id, 'ما كايناش وسائط محفوظة لهذا الكروب بعد.', show_alert=True)
                bot.copy_message(t, t, random.choice(media).message_id)
            elif d == 'mad:status':
                bot.edit_message_text(f'🧪 حالة المختبر\n\n🎯 الكروب: {t}\n💬 الكروبات المعروفة: {len(groups(runtime.db))}\n💾 الرسائل المستخدمة: {len(msgs)}\n🧠 AI: غير مطلوب للإرسال والعشوائي والوسائط\n📨 إرسال مباشر: جاهز\n⭐ Tip: من 1 إلى 1000', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
            elif d == 'mad:disable':
                save(runtime.db, chaos_target_chat_id=None, mad_waiting=False)
                bot.edit_message_text('🛑 تم إيقاف مختبر الميرفاوية وإلغاء الكروب المحدد.', c.message.chat.id, c.message.message_id, reply_markup=menu()); return
            bot.answer_callback_query(c.id, 'تم التنفيذ ✅')
        except Exception as e:
            bot.answer_callback_query(c.id, f'تعذر التنفيذ: {str(e)[:50]}', show_alert=True)

    @bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'animation', 'document', 'audio', 'voice', 'video_note'], func=lambda m: owner(m) and bool(state(runtime.db).get('mad_waiting')))
    def any_media(m):
        t = target(runtime.db)
        if t:
            try:
                bot.copy_message(t, m.chat.id, m.message_id)
                bot.send_message(m.chat.id, 'تم الإرسال للكروب المحدد بدون AI ✅')
            except Exception:
                bot.send_message(m.chat.id, 'ماقدرتش ننسخ هاد النوع ❌')
        else:
            bot.send_message(m.chat.id, 'اختار الكروب أولًا 🎯')
        save(runtime.db, mad_waiting=False)
