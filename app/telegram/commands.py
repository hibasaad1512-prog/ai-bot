from telebot.types import BotCommand, BotCommandScopeAllGroupChats

# Public command menu: only /start and /settings are advertised.
# /admin is deliberately absent from every Telegram command menu.
COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
    BotCommand("settings", "إعدادات الكروب (للمشرفين)"),
]


def install_commands(bot) -> None:
    try:
        # Private chats: only Start + Settings.
        bot.set_my_commands(COMMANDS)
        # Groups: only Start + Settings.
        bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllGroupChats())
    except Exception:
        pass
