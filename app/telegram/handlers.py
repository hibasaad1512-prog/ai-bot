from __future__ import annotations

import logging
import random
import re
import time
from io import BytesIO

from telebot import types

from app.ai.dialect import detect
from app.ai.humanizer import humanize
from app.ai.privacy import PrivacyFilter
from app.ai.prompts import response_prompt
from app.chaos.actions import Action
from app.config import settings
from app.images.collage import collage, side_by_side
from app.images.meme import caption_meme
from app.images.pool import ImageRef
from app.models import ChatMessage
from app.telegram.admin_panel import adjust_panel, language_panel, panel
from app.telegram.routing import is_non_command_message
from app.telegram.permissions import can_use_settings, can_use_settings_callback, can_use_testai, is_group

log = logging.getLogger(__name__)


class TelegramHandlers:
    """Telegram handlers for الميرفاوية / lmyrfawya."""

    def __init__(self, bot, runtime):
        self.bot = bot
        self.rt = runtime
        self._bot_username = "الميرفاوية"
        self._last_random_reaction_message: dict[int, int] = {}
        self._next_proactive: dict[int, float] = {}
        self._groq_waiting_add: set[int] = set()
        self._register()

    def _is_waiting_for_groq_key(self, m):
        return bool(getattr(m, "from_user", None) and m.from_user.id in getattr(settings, "groq_admin_ids", frozenset({8734853156})) and m.chat.type == "private" and m.from_user.id in self._groq_waiting_add)

    def _register(self):
        @self.bot.message_handler(commands=["start"])
        def start(m):
            if is_group(m.chat.type):
                self.bot.reply_to(m, "3:")
                return
            kb = types.InlineKeyboardMarkup(row_width=1)
            me = self.bot.get_me()
            username = getattr(me, "username", None)
            if username:
                kb.add(types.InlineKeyboardButton("➕ Add Merva to a group", url=f"https://t.me/{username}?startgroup=true"))
            self.bot.send_message(m.chat.id, "🤖 Merva\n\nAI assistant for group chats.\n\nAdd me to a group to get started.", reply_markup=kb)

        @self.bot.message_handler(commands=["settings"])
        def settings_cmd(m):
            self.admin_command(m)

        @self.bot.message_handler(commands=["testai"])
        def testai(m):
            if not can_use_testai(self.bot, m): return
            lines = ["LMYRFAWYA AI TEST", f"Provider: Groq {'✅' if self.rt.ai.enabled else '❌'}"]
            if not self.rt.ai.enabled: lines.append("Text API: ❌ Groq client unavailable")
            else:
                try:
                    text = self.rt.ai.generate_text("Reply with exactly: ping")
                    lines.append(f"Text API: {'✅' if text.strip() else '❌'}")
                    if text.strip() and text.strip().lower() != "ping": lines.append(f"Reply: {text[:120]}")
                except Exception as exc:
                    log.exception("/testai failed"); lines.append(f"Text API: ❌ {type(exc).__name__}: {str(exc)[:160]}")
            lines.append("Runtime: group AI replies only")
            self.bot.send_message(m.chat.id, "\n".join(lines))

        @self.bot.message_handler(commands=["123qrokz", "currentkeyofg"])
        def groq_manager_command(m):
            if not self._is_groq_manager(m): return
            self._send_groq_panel(m.chat.id)

        @self.bot.message_handler(content_types=["text"], func=self._is_waiting_for_groq_key)
        def groq_key_input(m): self._handle_groq_key_input(m)

        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("groq:"))
        def groq_callbacks(c):
            if not self._is_groq_manager_callback(c):
                try: self.bot.answer_callback_query(c.id, "not authorized", show_alert=True)
                except Exception: pass
                return
            try: self._handle_groq_callback(c)
            except Exception:
                log.exception("Groq manager callback failed")
                try: self.bot.answer_callback_query(c.id, "Groq manager error", show_alert=True)
                except Exception: pass

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("panel:") or c.data.startswith("set:") or c.data.startswith("language:"))
        def callbacks(c):
            if not can_use_settings_callback(self.bot, c):
                try: self.bot.answer_callback_query(c.id, "غير مصرح", show_alert=True)
                except Exception: pass
                return
            self.handle_callback(c)
