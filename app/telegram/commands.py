from __future__ import annotations
from telebot.types import BotCommand

COMMANDS = [
    BotCommand("start", "Start KYOOS"),
    BotCommand("settings", "Group settings (admins)"),
]

def install_commands(bot) -> None:
    try:
        bot.set_my_commands(COMMANDS)
    except Exception:
        # Command menu failure must never prevent the bot from handling updates.
        pass
