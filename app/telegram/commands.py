from __future__ import annotations

from telebot.types import BotCommand, BotCommandScopeChat

OWNER_ID = 8734853156

COMMANDS = [
    BotCommand("start", "Start lmyrfawy"),
    BotCommand("settings", "Group settings (admins)"),
]


def install_commands(bot) -> None:
    try:
        bot.set_my_commands(COMMANDS)
        # /admin appears only in the owner's private command menu.
        bot.set_my_commands(
            [BotCommand("admin", "Owner control panel")],
            scope=BotCommandScopeChat(chat_id=OWNER_ID),
        )
    except Exception:
        # Command menu failure must never prevent the bot from handling updates.
        pass
