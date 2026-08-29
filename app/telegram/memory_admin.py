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
        types.InlineKeyboardButton("🎛️ لوحة التحكم الرئيسية", callback_data="memadmin:home"),
        types.InlineKeyboardButton("🧪 مختبر الميرفاوية", callback_data="mad:open"),
        types.InlineKeyboardButton("🧠 الذاكرة", callback_data="memadmin:memory"),
        types.InlineKeyboardButton("🔑 مفاتيح الذكاء الاصطناعي", callback_data="memadmin:keys"),
        types.InlineKeyboardButton("💬 الرسائل والمحادثات", callback_data="memadmin:messages"),
        types.InlineKeyboardButton("🖼️ الصور والفيديو والوسائط", callback_data="memadmin:media"),
        types.InlineKeyboardButton("👤 المستخدمون", callback_data="memadmin:users"),
        types.InlineKeyboardButton("⚙️ تخصيص البوت", callback_data="memadmin:settings"),
        types.InlineKeyboardButton("🗄️ قاعدة البيانات", callback_data="memadmin:db"),
        types.InlineKeyboardButton("📊 الحالة والإحصائيات", callback_data="memadmin:status"),
    )
    return kb


def memory_menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📋 عرض ذكرياتي", callback_data="memadmin:listmem"),
        types.InlineKeyboardButton("🔎 البحث في الذاكرة", callback_data="memadmin:searchmem"),
        types.InlineKeyboardButton("➕ إضافة ذكرى", callback_data="memadmin:addmem"),
        types.InlineKeyboardButton("🗑️ نسيان ذكرى", callback_data="memadmin:forgetmem"),
        types.InlineKeyboardButton("💣 حذف كل الذكريات", callback_data="memadmin:clearmem"),
        types.InlineKeyboardButton("⬅️ رجوع", callback_data="memadmin:home"),
    )
    return kb


def key_menu() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📋 المفاتيح وحالتها", callback_data="memadmin:keylist"),
        types.InlineKeyboardButton("➕ إضافة مفتاح", callback_data="memadmin:keyadd"),
        types.InlineKeyboardButton("🗑️ حذف مفتاح", callback_data="memadmin:keydelete"),
        types.InlineKeyboardButton("🔄 اختبار المفاتيح", callback_data="memadmin:keytest"),
        types.InlineKeyboardButton("⬅️ رجوع", callback_data="memadmin:home"),
    )
    return kb
