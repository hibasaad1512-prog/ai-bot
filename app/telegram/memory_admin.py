from __future__ import annotations

from telebot import types
from app.config import settings

OWNER_ID = 8734853156


def is_owner(user_id: int | None) -> bool:
    if user_id is None: return False
    return int(user_id) in getattr(settings, "groq_admin_ids", frozenset({OWNER_ID}))


def menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎛️ Main Control", callback_data="memadmin:home"),
        types.InlineKeyboardButton("🧪 Merva Lab", callback_data="mad:open"),
        types.InlineKeyboardButton("🤖 Automation", callback_data="auto:home"),
        types.InlineKeyboardButton("🧠 Memory", callback_data="memadmin:memory"),
        types.InlineKeyboardButton("🔑 AI Keys", callback_data="memadmin:keys"),
        types.InlineKeyboardButton("💬 Messages", callback_data="memadmin:messages"),
        types.InlineKeyboardButton("🖼️ Media", callback_data="memadmin:media"),
        types.InlineKeyboardButton("👤 Users", callback_data="memadmin:users"),
        types.InlineKeyboardButton("⚙️ Bot Settings", callback_data="memadmin:settings"),
        types.InlineKeyboardButton("🗄️ Database", callback_data="memadmin:db"),
        types.InlineKeyboardButton("📊 Status", callback_data="memadmin:status"),
    )
    return kb


def memory_menu() -> types.InlineKeyboardMarkup:
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📋 Memories",callback_data="memadmin:listmem"),types.InlineKeyboardButton("🔎 Search",callback_data="memadmin:searchmem"),types.InlineKeyboardButton("➕ Add",callback_data="memadmin:addmem"),types.InlineKeyboardButton("🗑️ Forget",callback_data="memadmin:forgetmem"),types.InlineKeyboardButton("💣 Clear all",callback_data="memadmin:clearmem"),types.InlineKeyboardButton("⬅️ Back",callback_data="memadmin:home"))
    return kb


def key_menu() -> types.InlineKeyboardMarkup:
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📋 Keys & status",callback_data="memadmin:keylist"),types.InlineKeyboardButton("➕ Add key",callback_data="memadmin:keyadd"),types.InlineKeyboardButton("🗑️ Delete key",callback_data="memadmin:keydelete"),types.InlineKeyboardButton("🔄 Test keys",callback_data="memadmin:keytest"),types.InlineKeyboardButton("⬅️ Back",callback_data="memadmin:home"))
    return kb
