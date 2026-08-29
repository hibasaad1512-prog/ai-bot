from telebot.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeChat

OWNER_ID = 8734853156

# Private menu for everyone: /start only.
PUBLIC_COMMANDS = [
    BotCommand("start", "Start Merva"),
]

# Group menu: /start + /settings.
GROUP_COMMANDS = [
    BotCommand("start", "Start Merva"),
    BotCommand("settings", "Group Settings (Admins)"),
]


def install_commands(bot) -> None:
    try:
        # Regular private users: only /start.
        bot.set_my_commands(PUBLIC_COMMANDS)
        # Groups: /start + /settings.
        bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
        # Owner's private chat: still only /start. /admin stays completely secret.
        bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeChat(chat_id=OWNER_ID))
    except Exception:
        pass
