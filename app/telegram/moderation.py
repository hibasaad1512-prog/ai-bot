from __future__ import annotations
import logging
from telebot import types

ADMIN_ID = 8734853156


def _is_owner(message):
    u = getattr(message, 'from_user', None)
    return bool(u and int(u.id) == ADMIN_ID)


def register(bot, runtime):
    @bot.message_handler(commands=['del', 'delete'])
    def delete_reply(message):
        if not _is_owner(message):
            return
        target = getattr(message, 'reply_to_message', None)
        if not target or getattr(message.chat, 'type', None) not in ('group', 'supergroup'):
            bot.reply_to(message, '🗑️ رد على الرسالة التي تريد حذفها ثم اكتب /del')
            return
        try:
            bot.delete_message(message.chat.id, target.message_id)
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
        except Exception as exc:
            bot.reply_to(message, '❌ لم أستطع حذف الرسالة. تأكد أن البوت Admin ولديه Delete messages.')
            logging.getLogger(__name__).warning('delete reply failed: %s', exc)

    @bot.message_handler(commands=['delmenu'])
    def delete_menu(message):
        if not _is_owner(message) or getattr(message.chat, 'type', None) not in ('group', 'supergroup'):
            return
        try:
            rows = runtime.db.recent_messages(message.chat.id, 15)
        except Exception:
            rows = []
        if not rows:
            bot.reply_to(message, '🗑️ لا توجد رسائل محفوظة.')
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for row in reversed(rows):
            mid = getattr(row, 'message_id', None)
            if not mid:
                continue
            text = (getattr(row, 'text', None) or getattr(row, 'caption', None) or '📎 رسالة/وسائط').replace('\n', ' ')
            text = text[:45]
            markup.add(types.InlineKeyboardButton(f'🗑️ {text}', callback_data=f'delmsg:{message.chat.id}:{mid}'))
        markup.add(types.InlineKeyboardButton('⬅️ إغلاق', callback_data='delmsg:close'))
        bot.reply_to(message, '🗑️ آخر الرسائل — اختر واحدة لحذفها:', reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('delmsg:'))
    def delete_callback(call):
        if not _is_owner(call.message):
            bot.answer_callback_query(call.id, 'Not authorized', show_alert=True)
            return
        if call.data == 'delmsg:close':
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            return
        try:
            _, chat_id, message_id = call.data.split(':', 2)
            bot.delete_message(int(chat_id), int(message_id))
            bot.answer_callback_query(call.id, '🗑️ تم الحذف')
            try:
                bot.edit_message_text('🗑️ تم حذف الرسالة.\nاستخدم /delmenu لعرض آخر الرسائل.', call.message.chat.id, call.message.message_id)
            except Exception:
                pass
        except Exception as exc:
            bot.answer_callback_query(call.id, '❌ فشل الحذف: تأكد من صلاحيات البوت', show_alert=True)
            logging.getLogger(__name__).warning('delete menu callback failed: %s', exc)
