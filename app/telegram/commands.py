from __future__ import annotations

from telebot.types import BotCommand

COMMANDS = [
    BotCommand("start", "Start lmyrfawy"),
    BotCommand("settings", "Group settings (admins)"),
    BotCommand("remember", "Save a permanent memory"),
    BotCommand("memory", "Show your saved memories"),
    BotCommand("forget", "Delete a saved memory"),
    BotCommand("clear_memory", "Delete all your memories"),
]


def install_commands(bot) -> None:
    try:
        bot.set_my_commands(COMMANDS)
    except Exception:
        # Command menu failure must never prevent the bot from handling updates.
        pass
