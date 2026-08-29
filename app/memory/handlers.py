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
        # These legacy commands are owner-only now; the visible control surface
        # is the single /admin command.
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

        @self.bot.callback_query_handler(
            func=lambda c: bool(c.data) and c.data.startswith("memadmin:")
        )
        def admin_callback(call):
            if not is_owner(getattr(call.from_user, "id", None)):
                try:
                    self.bot.answer_callback_query(call.id, "Not authorized", show_alert=True)
                except Exception:
                    pass
                return
            try:
                self._admin_callback(call)
            except Exception:
                self.bot.answer_callback_query(call.id, "Operation failed", show_alert=True)

        @self.bot.message_handler(
            content_types=["text"],
            func=lambda m: is_owner(getattr(m.from_user, "id", None))
            and getattr(m.from_user, "id", None) in self._admin_waiting,
        )
        def admin_input(message):
            self._handle_admin_input(message)

    @staticmethod
    def _args(message) -> str:
        value = getattr(message, "text", "") or ""
        return value.split(" ", 1)[1].strip() if " " in value else ""

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

    def _target_chat(self, user_id: int, fallback: int) -> int:
        return int(self._admin_context.get(user_id, fallback))

    def _open_admin(self, message):
        user_id = int(message.from_user.id)
        self._admin_context[user_id] = int(message.chat.id)
        if getattr(message.chat, "type", "") != "private":
            try:
                self.bot.send_message(
                    user_id,
                    "🔐 لوحة تحكم المالك — هذه الرسالة خاصة بك.\n"
                    f"المحادثة المحددة: {message.chat.title or message.chat.id}",
                    reply_markup=menu(),
                )
                self.bot.reply_to(message, "📩 أرسلت لك لوحة الإدارة على الخاص.")
                return
            except Exception:
                pass
        self.bot.send_message(message.chat.id, "🔐 لوحة تحكم المالك", reply_markup=menu())

    def _edit(self, call, text_value, markup=None):
        try:
            self.bot.edit_message_text(
                text_value,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
            )
        except Exception:
            self.bot.send_message(call.message.chat.id, text_value, reply_markup=markup)

    def _admin_callback(self, call):
        data = call.data
        self.bot.answer_callback_query(call.id)
        if data == "memadmin:back":
            self._edit(call, "🔐 لوحة تحكم المالك", menu())
        elif data == "memadmin:memory":
            self._edit(call, "🧠 إدارة الذاكرة", memory_menu())
        elif data == "memadmin:keys":
            self._edit(call, "🔑 إدارة مفاتيح AI", key_menu())
        elif data == "memadmin:listmem":
            self._admin_list_memory(call)
        elif data == "memadmin:searchmem":
            self._ask(call, "search_memory", "🔎 أرسل كلمة البحث عن الذاكرة:")
        elif data == "memadmin:addmem":
            self._ask(call, "add_memory", "➕ أرسل الذاكرة التي تريد حفظها:")
        elif data == "memadmin:forgetmem":
            self._ask(call, "forget_memory", "🗑 أرسل رقم الذاكرة أو كلمة منها لحذفها:")
        elif data == "memadmin:clearmem":
            self._confirm_clear_memory(call)
        elif data == "memadmin:clearmem_yes":
            target = self._target_chat(int(call.from_user.id), call.message.chat.id)
            count = self.store.clear(target, int(call.from_user.id))
            self._edit(call, f"🧹 Deleted {count} memories from the selected chat.", memory_menu())
        elif data == "memadmin:messages":
            self._admin_messages(call)
        elif data == "memadmin:messages_yes":
            target = self._target_chat(int(call.from_user.id), call.message.chat.id)
            with self.rt.db.engine.begin() as conn:
                result = conn.execute(text("DELETE FROM chat_messages WHERE chat_id=:chat_id"), {"chat_id": target})
            self._edit(call, f"🧹 Deleted {int(result.rowcount or 0)} stored messages.", menu())
        elif data == "memadmin:media":
            self._admin_media(call)
        elif data == "memadmin:users":
            self._admin_users(call)
        elif data == "memadmin:db":
            self._admin_db(call)
        elif data == "memadmin:keylist":
            self._admin_keys(call)
        elif data == "memadmin:keyadd":
            self._ask(call, "add_key", "🔑 أرسل Groq API key. لن أعرضه في الرد:")
        elif data == "memadmin:keydelete":
            self._ask(call, "delete_key", "🗑 أرسل رقم المفتاح الذي تريد حذفه:")

    def _ask(self, call, action: str, prompt: str):
        self._admin_waiting[int(call.from_user.id)] = action
        self._edit(call, prompt)

    def _admin_list_memory(self, call):
        target = self._target_chat(int(call.from_user.id), call.message.chat.id)
        items = self.store.list_memories(target, int(call.from_user.id), 50)
        if not items:
            self._edit(call, "🧠 لا توجد ذكريات في المحادثة المحددة.", memory_menu())
            return
        lines = ["🧠 ذكريات المالك:", ""]
        for item in items[:40]:
            lines.append(f"#{item['id']} — {item['memory_value'][:350]}")
        self._edit(call, "\n".join(lines), memory_menu())

    def _confirm_clear_memory(self, call):
        kb = tg_types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            tg_types.InlineKeyboardButton("✅ نعم احذف", callback_data="memadmin:clearmem_yes"),
            tg_types.InlineKeyboardButton("❌ إلغاء", callback_data="memadmin:memory"),
        )
        self._edit(call, "⚠️ سيحذف كل ذكرياتك في المحادثة المحددة. متأكد؟", kb)

    def _admin_messages(self, call):
        target = self._target_chat(int(call.from_user.id), call.message.chat.id)
        with self.rt.db.engine.connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) AS n FROM chat_messages WHERE chat_id=:chat_id"), {"chat_id": target}).mappings().first()
        n = int(row["n"] if row else 0)
        kb = tg_types.InlineKeyboardMarkup(row_width=1)
        kb.add(tg_types.InlineKeyboardButton("🧹 Delete stored messages", callback_data="memadmin:messages_yes"))
        kb.add(tg_types.InlineKeyboardButton("⬅️ Back", callback_data="memadmin:back"))
        self._edit(call, f"💬 Stored messages in selected chat: {n}", kb)

    def _admin_media(self, call):
        total = 0
        try:
            target = self._target_chat(int(call.from_user.id), call.message.chat.id)
            total = self.rt.images.count(target)
        except Exception:
            pass
        self._edit(call, f"🖼 Media cache in selected chat: {total}\n\nTelegram file_id is used; actual image files are not stored on the server.", menu())

    def _admin_users(self, call):
        with self.rt.db.engine.connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) AS n FROM users")).mappings().first()
        n = int(row["n"] if row else 0)
        self._edit(call, f"👤 Registered users: {n}", menu())

    def _admin_db(self, call):
        with self.rt.db.engine.connect() as conn:
            users = conn.execute(text("SELECT COUNT(*) AS n FROM users")).scalar() or 0
            memories = conn.execute(text("SELECT COUNT(*) AS n FROM memory")).scalar() or 0
            messages = conn.execute(text("SELECT COUNT(*) AS n FROM chat_messages")).scalar() or 0
        self._edit(call, f"🗄 Database OK ✅\nUsers: {users}\nMemories: {memories}\nMessages: {messages}\nNeon is the persistent store.", menu())

    def _admin_keys(self, call):
        ai = self.rt.ai
        lines = [f"🔑 AI keys: {len(getattr(ai, 'keys', []))}"]
        for i, key in enumerate(getattr(ai, "keys", []), 1):
            status = getattr(ai, "key_status", {}).get(key, {}).get("status", "unknown")
            lines.append(f"{i}. {ai.mask_key(key)} — {status}")
        lines.append(f"Current: #{getattr(ai, 'current_key_number', None) or '-'}")
        self._edit(call, "\n".join(lines), key_menu())

    def _handle_admin_input(self, message):
        user_id = int(message.from_user.id)
        action = self._admin_waiting.pop(user_id, None)
        if not action:
            return
        value = (getattr(message, "text", "") or "").strip()
        try:
            target = self._target_chat(user_id, message.chat.id)
            if action == "add_memory":
                self.store.remember(target, user_id, value)
                self.bot.send_message(message.chat.id, "🧠 Saved.", reply_markup=menu())
            elif action == "forget_memory":
                count = self.store.forget(target, user_id, value)
                self.bot.send_message(message.chat.id, f"🗑 Deleted: {count}", reply_markup=menu())
            elif action == "search_memory":
                items = self.store.search(target, user_id, value, 20)
                body = "\n".join(f"#{x['id']} — {x['memory_value'][:500]}" for x in items) or "No matches."
                self.bot.send_message(message.chat.id, "🔎 Results:\n" + body, reply_markup=menu())
            elif action == "add_key":
                ok, status = self.rt.ai.add_key(value)
                self.bot.send_message(message.chat.id, f"🔑 {'Added ✅' if ok else 'Rejected ❌'} ({status})", reply_markup=menu())
            elif action == "delete_key":
                index = int(value) - 1
                ok = self.rt.ai.delete_key(index)
                self.bot.send_message(message.chat.id, f"🗑 {'Deleted ✅' if ok else 'Not found ❌'}", reply_markup=menu())
        except Exception:
            self.bot.send_message(message.chat.id, "❌ Operation failed. No secret was printed.", reply_markup=menu())
