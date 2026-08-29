from telebot.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeChat

OWNER_ID = 8734853156

# Public menu for everyone else: /start only.
PUBLIC_COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
]

# Group menu: Start + Settings.
GROUP_COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
    BotCommand("settings", "إعدادات الكروب (للمشرفين)"),
]


def install_commands(bot) -> None:
    try:
        # Everyone's private chat: only /start.
        bot.set_my_commands(PUBLIC_COMMANDS)
        # Groups: /start + /settings.
        bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
        # Owner's private chat: deliberately still only /start.
        # /admin is secret and must be typed manually; never advertise it.
        bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeChat(chat_id=OWNER_ID))
    except Exception:
        pass
