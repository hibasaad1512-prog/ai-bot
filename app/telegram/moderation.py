from __future__ import annotations
import logging
from telebot import types
from app.telegram.memory_admin import is_owner

log = logging.getLogger(__name__)


def register(bot, runtime):
    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('delmsg:'))
    def delete_callback(call):
        uid = getattr(getattr(call, 'from_user', None), 'id', None)
        if not is_owner(uid):
            bot.answer_callback_query(call.id, 'Not authorized', show_alert=True)
            return
        data = call.data
        try:
            bot.answer_callback_query(call.id)
            if data == 'delmsg:open':
                chats = []
                try:
                    for cid in runtime.db.list_chat_ids():
                        try:
                            ch = bot.get_chat(cid)
                            title = getattr(ch, 'title', None) or getattr(ch, 'username', None) or str(cid)
                        except Exception:
                            title = str(cid)
                        chats.append((int(cid), title))
                except Exception:
                    chats = []
                kb = types.InlineKeyboardMarkup(row_width=1)
                for cid, title in chats[:100]:
                    kb.add(types.InlineKeyboardButton(f'🗑️ {str(title)[:50]}', callback_data=f'delmsg:chat:{cid}'))
                kb.add(types.InlineKeyboardButton('⬅️ Back', callback_data='owner:back'))
                bot.edit_message_text('🗑️ Delete a message\n\nChoose a group:', call.message.chat.id, call.message.message_id, reply_markup=kb)
                return
            if data.startswith('delmsg:chat:'):
                cid = int(data.split(':')[-1])
                rows = runtime.db.recent_messages(cid, 15)
                kb = types.InlineKeyboardMarkup(row_width=1)
                for row in reversed(rows):
                    mid = getattr(row, 'message_id', None)
                    if not mid:
                        continue
                    text = (getattr(row, 'text', None) or '📎 Media').replace('\n', ' ')[:45]
                    kb.add(types.InlineKeyboardButton(f'🗑️ {text}', callback_data=f'delmsg:item:{cid}:{int(mid)}'))
                kb.add(types.InlineKeyboardButton('⬅️ Groups', callback_data='delmsg:open'))
                bot.edit_message_text('🗑️ Choose a recent message to delete:', call.message.chat.id, call.message.message_id, reply_markup=kb)
                return
            if data.startswith('delmsg:item:'):
                _, _, cid, mid = data.split(':', 3)
                bot.delete_message(int(cid), int(mid))
                bot.answer_callback_query(call.id, '🗑️ Deleted')
                bot.edit_message_text('🗑️ Message deleted.', call.message.chat.id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton('⬅️ Back', callback_data='owner:back')))
                return
        except Exception as exc:
            log.warning('owner delete tool failed: %s', exc)
            try:
                bot.answer_callback_query(call.id, '❌ Cannot delete. Check bot admin/Delete Messages permission.', show_alert=True)
            except Exception:
                pass
