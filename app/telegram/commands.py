from telebot.types import BotCommand, BotCommandScopeAllGroupChats

# Public commands only. /admin is deliberately absent from every Telegram menu.
COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
    BotCommand("settings", "إعدادات الكروب (للمشرفين)"),
]


def install_commands(bot) -> None:
    try:
        # Keep the same public menu in private chats and groups.
        # /admin is handled manually and is never advertised by Telegram.
        bot.set_my_commands(COMMANDS)
        bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllGroupChats())
    except Exception:
        pass
