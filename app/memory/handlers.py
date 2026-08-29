from __future__ import annotations

import types

from sqlalchemy import text
from telebot import types as tg_types

from app.memory.store import MemoryStore
from app.telegram.memory_admin import is_owner, menu, memory_menu, key_menu


class MemoryHandlers:
    """Persistent memory commands plus a private owner-only admin panel."""

    def __init__(self, bot, runtime, handlers):
        self.bot = bot
        self.rt = runtime
        self.handlers = handlers
        self.store = MemoryStore(runtime.db)
        self._admin_waiting: dict[int, str] = {}
        self._admin_context: dict[int, int] = {}
        self._patch_message_tracking()
        self._patch_context()
        self._register()

    def _patch_message_tracking(self):
        original = getattr(self.handlers, "on_message", None)
        if not callable(original):
            # Older/partial TelegramHandlers builds do not expose on_message.
            # Memory must never prevent the bot from starting in that case.
            return
        store = self.store

        def wrapped(instance, message):
            try:
                user = getattr(message, "from_user", None)
                if user and not getattr(user, "is_bot", False):
                    store.touch_user(int(user.id), getattr(user, "username", None), getattr(user, "first_name", None))
            except Exception:
                pass
            return original(message)

        self.handlers.on_message = types.MethodType(wrapped, self.handlers)

    def _patch_context(self):
        original = getattr(self.handlers, "_build_ai_context", None)
        if not callable(original):
            # Context integration is optional; do not crash startup if the
            # Telegram handler implementation does not expose this hook.
            return
        store = self.store

        def wrapped(instance, message, current_text):
            context, mode = original(message, current_text)
            try:
                user = getattr(message, "from_user", None)
                if user:
                    memories = store.search(message.chat.id, user.id, current_text, 8)
                    if not memories:
                        memories = store.list_memories(message.chat.id, user.id, 8)
                    memory_text = store.format_for_prompt(memories)
                    if memory_text:
                        context = context + "\n\n" + memory_text
            except Exception:
                pass
            return context, mode

        self.handlers._build_ai_context = types.MethodType(wrapped, self.handlers)

    def _register(self):
        @self.bot.message_handler(commands=["remember"])
        def remember(message):
            if is_owner(getattr(message.from_user, "id", None)):
                self._remember(message)

        @self.bot.message_handler(commands=["memory"])
        def memory(message):
            if is_owner(getattr(message.from_user, "id", None)):
                self._list(message)

        @self.bot.message_handler(commands=["forget"])
        def forget(message):
            if is_owner(getattr(message.from_user, "id", None)):
                self._forget(message)

        @self.bot.message_handler(commands=["clear_memory"])
        def clear_memory(message):
            if is_owner(getattr(message.from_user, "id", None)):
                self._clear(message)

        @self.bot.message_handler(commands=["admin"])
        def admin(message):
            if not is_owner(getattr(message.from_user, "id", None)):
                return
            self._open_admin(message)

        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("memadmin:"))
        def admin_callback(call):
            if not is_owner(getattr(call.from_user, "id", None)):
                try: self.bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                except Exception: pass
                return
            self._admin_callback(call)
