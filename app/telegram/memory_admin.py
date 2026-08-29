from __future__ import annotations

from telebot import types

from app.config import settings

OWNER_ID = 8734853156


def is_owner(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return int(user_id) in getattr(settings, "groq_admin_ids", frozenset({OWNER_ID}))


def menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧪 Merva Lab", callback_data="memadmin:lab"),
        types.InlineKeyboardButton("🧠 Memory", callback_data="memadmin:memory"),
        types.InlineKeyboardButton("🔑 AI Keys", callback_data="memadmin:keys"),
        types.InlineKeyboardButton("💬 Messages", callback_data="memadmin:messages"),
        types.InlineKeyboardButton("🖼 Media", callback_data="memadmin:media"),
        types.InlineKeyboardButton("👤 Users", callback_data="memadmin:users"),
        types.InlineKeyboardButton("🗄 Database", callback_data="memadmin:db"),
    )
    return kb


def memory_menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📋 My memories", callback_data="memadmin:listmem"),
        types.InlineKeyboardButton("🔎 Search", callback_data="memadmin:searchmem"),
        types.InlineKeyboardButton("➕ Remember", callback_data="memadmin:addmem"),
        types.InlineKeyboardButton("🗑 Forget", callback_data="memadmin:forgetmem"),
        types.InlineKeyboardButton("💣 Delete all", callback_data="memadmin:clearmem"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="memadmin:back"),
    )
    return kb


def key_menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📋 Key status", callback_data="memadmin:keylist"),
        types.InlineKeyboardButton("➕ Add key", callback_data="memadmin:keyadd"),
        types.InlineKeyboardButton("🗑 Delete key", callback_data="memadmin:keydelete"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="memadmin:back"),
    )
    return kb
