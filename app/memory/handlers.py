from __future__ import annotations

import types

from app.memory.store import MemoryStore


class MemoryHandlers:
    """Telegram commands and prompt integration for persistent user memory."""

    def __init__(self, bot, runtime, handlers):
        self.bot = bot
        self.rt = runtime
        self.handlers = handlers
        self.store = MemoryStore(runtime.db)
        self._patch_message_tracking()
        self._patch_context()
        self._register()

    def _patch_message_tracking(self):
        original = self.handlers.on_message
        store = self.store

        def wrapped(instance, message):
            try:
                user = getattr(message, "from_user", None)
                if user and not getattr(user, "is_bot", False):
                    store.touch_user(
                        int(user.id),
                        getattr(user, "username", None),
                        getattr(user, "first_name", None),
                    )
            except Exception:
                pass
            return original(message)

        self.handlers.on_message = types.MethodType(wrapped, self.handlers)

    def _patch_context(self):
        original = self.handlers._build_ai_context
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
            self._remember(message)

        @self.bot.message_handler(commands=["memory"])
        def memory(message):
            self._list(message)

        @self.bot.message_handler(commands=["forget"])
        def forget(message):
            self._forget(message)

        @self.bot.message_handler(commands=["clear_memory"])
        def clear_memory(message):
            self._clear(message)

    @staticmethod
    def _args(message) -> str:
        text = getattr(message, "text", "") or ""
        return text.split(" ", 1)[1].strip() if " " in text else ""

    def _remember(self, message):
        value = self._args(message)
        if not value:
            self.bot.reply_to(message, "اكتب المعلومة بعد الأمر. مثال: /remember يحب القهوة")
            return
        try:
            self.store.remember(message.chat.id, message.from_user.id, value)
            self.bot.reply_to(message, "🧠 تم حفظها في الذاكرة الدائمة.")
        except Exception:
            self.bot.reply_to(message, "❌ تعذر حفظ المعلومة الآن.")

    def _list(self, message):
        try:
            items = self.store.list_memories(message.chat.id, message.from_user.id)
            if not items:
                self.bot.reply_to(message, "🧠 ذاكرتك فارغة حاليًا.")
                return
            lines = ["🧠 ذاكرتك الدائمة:", ""]
            for item in items:
                lines.append(f"#{item['id']} — {item['memory_value'][:500]}")
            self.bot.reply_to(message, "\n".join(lines[:51]))
        except Exception:
            self.bot.reply_to(message, "❌ تعذر قراءة الذاكرة الآن.")

    def _forget(self, message):
        selector = self._args(message)
        if not selector:
            self.bot.reply_to(message, "استخدم /forget رقم الذاكرة أو كلمة منها.")
            return
        try:
            count = self.store.forget(message.chat.id, message.from_user.id, selector)
            self.bot.reply_to(message, "🗑️ تم حذف الذاكرة." if count else "لم أجد ذاكرة مطابقة.")
        except Exception:
            self.bot.reply_to(message, "❌ تعذر حذف الذاكرة الآن.")

    def _clear(self, message):
        try:
            count = self.store.clear(message.chat.id, message.from_user.id)
            self.bot.reply_to(message, f"🧹 تم حذف {count} من الذكريات الدائمة.")
        except Exception:
            self.bot.reply_to(message, "❌ تعذر مسح الذاكرة الآن.")
