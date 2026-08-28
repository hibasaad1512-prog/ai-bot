from __future__ import annotations
from app.config import settings


def is_global_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids


def is_group(chat_type: str) -> bool:
    return chat_type in {"group", "supergroup"}


def is_group_admin(bot, chat_id: int, user_id: int) -> bool:
    """True only when Telegram confirms the user is an admin/creator in this chat."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in {"administrator", "creator"}
    except Exception:
        return False


def can_use_settings(bot, message) -> bool:
    """Settings are group-admin-only; private chats are never eligible."""
    if not is_group(message.chat.type):
        return False
    return is_group_admin(bot, message.chat.id, message.from_user.id)


def can_use_testai(bot, message) -> bool:
    """testai works in private and groups, but remains admin-gated."""
    if is_global_admin(message.from_user.id):
        return True
    return is_group(message.chat.type) and is_group_admin(bot, message.chat.id, message.from_user.id)


def can_use_settings_callback(bot, callback) -> bool:
    chat = getattr(callback.message, "chat", None)
    user = getattr(callback, "from_user", None)
    if not chat or not user or not is_group(chat.type):
        return False
    return is_group_admin(bot, chat.id, user.id)
