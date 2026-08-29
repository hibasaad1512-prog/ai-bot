from __future__ import annotations

import logging
import random

import telebot

from app.config import settings
from app.runtime import Runtime
from app.telegram.commands import install_commands
from app.telegram.handlers import TelegramHandlers
from app.telegram.chaos_admin import register as register_chaos_admin
from app.memory.handlers import MemoryHandlers
from app.worker.scheduler import ProactiveScheduler

log = logging.getLogger(__name__)


class KyoosBot:
    def __init__(self, token: str | None = None):
        self.token = token or settings.telegram_bot_token
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

        self.bot = telebot.TeleBot(
            self.token,
            parse_mode=None,
            threaded=True,
            num_threads=4,
        )
        self.runtime = Runtime()
        self.handlers = TelegramHandlers(self.bot, self.runtime)
        self.memory_handlers = MemoryHandlers(
            self.bot,
            self.runtime,
            self.handlers,
        )
        # Private owner-only lab: choose a known group and send controlled random
        # experiments there using content already seen by the bot.
        register_chaos_admin(self.bot, self.runtime)

        try:
            me = self.bot.get_me()
            self.handlers._bot_username = (me.username or "").lower()
        except Exception:
            self.handlers._bot_username = ""
            log.exception("Telegram getMe failed")

        install_commands(self.bot)
        self._configure_webhook()
        self._start_proactive()

    def _configure_webhook(self):
        if not settings.public_base_url:
            log.warning("Telegram webhook NOT configured: PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is missing")
            return

        try:
            url = f"{settings.public_base_url}/telegram/webhook"
            self.bot.remove_webhook()
            self.bot.set_webhook(
                url=url,
                secret_token=settings.webhook_secret or None,
            )
            info = self.bot.get_webhook_info()
            log.info(
                "telegram webhook configured: url=%s pending=%s last_error=%s",
                info.url,
                info.pending_update_count,
                info.last_error_message or "none",
            )
        except Exception:
            log.exception("webhook setup failed; bot will still serve incoming requests if webhook exists")

    def _start_proactive(self):
        if not settings.enabled_proactive:
            return
        self.scheduler = ProactiveScheduler(self._proactive_tick)
        self.scheduler.start()

    def _proactive_tick(self):
        chat_ids = list(self.runtime.memory._data.keys())
        if not chat_ids:
            return
        self.handlers.proactive(random.choice(chat_ids))

    def process(self, update):
        self.bot.process_new_updates([update])
