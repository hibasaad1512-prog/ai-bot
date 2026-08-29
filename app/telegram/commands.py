from telebot.types import BotCommand, BotCommandScopeChat

OWNER_ID = 8734853156

COMMANDS = [
    BotCommand("start", "Start lmyrfawy"),
    BotCommand("settings", "Group settings (admins)"),
]

OWNER_COMMANDS = [
    BotCommand("admin", "Owner GOD PANEL"),
]


def install_commands(bot) -> None:
    try:
        bot.set_my_commands(COMMANDS)
        bot.set_my_commands(
            OWNER_COMMANDS,
            scope=BotCommandScopeChat(chat_id=OWNER_ID),
        )
    except Exception:
        pass
