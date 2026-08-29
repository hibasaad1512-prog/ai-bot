from telebot.types import BotCommand, BotCommandScopeAllGroupChats

OWNER_ID = 8734853156

# Public commands only. /admin is deliberately absent from every Telegram menu.
COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
    BotCommand("settings", "إعدادات الكروب (للمشرفين)"),
]


def install_commands(bot) -> None:
    try:
        bot.set_my_commands(COMMANDS)
        bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllGroupChats())
    except Exception:
        pass
