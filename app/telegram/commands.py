from telebot.types import BotCommand, BotCommandScopeChat, BotCommandScopeAllGroupChats

OWNER_ID = 8734853156

# Public commands: only these are advertised in chats.
COMMANDS = [
    BotCommand("start", "بدء الميرفاوية"),
    BotCommand("settings", "إعدادات الكروب (للمشرفين)"),
]

# Owner-only: Telegram shows this only in the owner's private chat.
OWNER_COMMANDS = [
    BotCommand("admin", "لوحة التحكم السرية"),
]


def install_commands(bot) -> None:
    try:
        # Private/general command menu.
        bot.set_my_commands(COMMANDS)
        # Explicitly keep the group menu limited to Start + Settings.
        bot.set_my_commands(
            COMMANDS,
            scope=BotCommandScopeAllGroupChats(),
        )
        # Secret owner menu is visible only in the owner's private chat.
        bot.set_my_commands(
            OWNER_COMMANDS,
            scope=BotCommandScopeChat(chat_id=OWNER_ID),
        )
    except Exception:
        pass
