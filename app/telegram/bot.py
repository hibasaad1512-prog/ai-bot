from __future__ import annotations
import logging
import telebot
from app.config import settings
from app.runtime import Runtime
from app.telegram.handlers import TelegramHandlers
from app.worker.scheduler import ProactiveScheduler
from app.telegram.commands import install_commands
import random

log=logging.getLogger(__name__)
class KyoosBot:
    def __init__(self,token:str|None=None):
        self.token=token or settings.telegram_bot_token
        if not self.token:raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        self.bot=telebot.TeleBot(self.token,parse_mode=None,threaded=True,num_threads=4)
        self.runtime=Runtime(); self.handlers=TelegramHandlers(self.bot,self.runtime)
        try:
            self._bot_username=(self.bot.get_me().username or "").lower()
        except Exception:
            self._bot_username=""
        self.handlers._bot_username=self._bot_username
        install_commands(self.bot)
        self.register_auto_handler(); self._configure_webhook(); self._start_proactive()
    def _configure_webhook(self):
        if not settings.public_base_url:
            log.warning("Telegram webhook NOT configured: PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is missing")
            return
        try:
            url=f"{settings.public_base_url}/telegram/webhook"
            self.bot.remove_webhook()
            self.bot.set_webhook(url=url, secret_token=settings.webhook_secret or None)
            info=self.bot.get_webhook_info()
            log.info("telegram webhook configured: url=%s pending=%s last_error=%s", info.url, info.pending_update_count, info.last_error_message or "none")
        except Exception:
            log.exception("webhook setup failed; continuing without crash")

    def _start_proactive(self):
        if not settings.enabled_proactive:
            return
        self.scheduler=ProactiveScheduler(self._proactive_tick)
        self.scheduler.start()

    def _proactive_tick(self):
        chat_ids=list(self.runtime.memory._data.keys())
        if not chat_ids:return
        chat_id=random.choice(chat_ids)
        self.handlers.proactive(chat_id)

    def register_auto_handler(self):
        @self.bot.message_handler(content_types=["text","photo"])
        def all_messages(m):
            if m.text and m.text.startswith("/start"):return
            if m.text and m.text.startswith("/"):return
            self.handlers.on_message(m)
        @self.bot.message_handler(commands=["settings"])
        def settings_cmd(m):self.handlers.admin_command(m)
        @self.bot.message_handler(func=lambda m: True,content_types=["text"])
        def game_join(m):
            if not m.text:return
            if m.text.strip().upper()=="JOIN":
                if self.runtime.games.join(m.chat.id,m.from_user.id): self.bot.reply_to(m,"joined")
    def process(self,update):self.bot.process_new_updates([update])
