from __future__ import annotations
import logging, random, time
import telebot
from app.config import settings
from app.runtime import Runtime
from app.telegram.commands import install_commands
from app.telegram.handlers import TelegramHandlers
from app.telegram.chaos_admin import register as register_chaos_admin
from app.telegram.owner_controls import register as register_owner_controls
from app.telegram.moderation import register as register_moderation
from app.telegram.memory_admin import is_owner, menu as god_menu
from app.memory.handlers import MemoryHandlers
from app.worker.scheduler import ProactiveScheduler
from app.worker.media_automation import MediaAutomation
from app.storage import register_smart_archive
log=logging.getLogger(__name__)

class KyoosBot:
    def __init__(self,token:str|None=None):
        self.token=token or settings.telegram_bot_token
        if not self.token: raise RuntimeError('TELEGRAM_BOT_TOKEN is required')
        self.bot=telebot.TeleBot(self.token,parse_mode=None,threaded=True,num_threads=4)
        self.runtime=Runtime()
        @self.bot.message_handler(commands=['start'])
        def public_start(message):
            if getattr(message.chat,'type','') in ('group','supergroup'):
                self.bot.reply_to(message,'3:'); return
            kb=telebot.types.InlineKeyboardMarkup(row_width=1)
            try: username=getattr(self.bot.get_me(),'username',None)
            except Exception: username=None
            if username: kb.add(telebot.types.InlineKeyboardButton('➕ Add Merva to a group',url=f'https://t.me/{username}?startgroup=true'))
            self.bot.send_message(message.chat.id,'🤖 Merva\n\nAI assistant for group chats.\n\nAdd me to a group to get started.',reply_markup=kb)
        @self.bot.message_handler(commands=['admin'])
        def god_panel(message):
            if not is_owner(getattr(message.from_user,'id',None)): return
            if getattr(message.chat,'type','')!='private':
                try:self.bot.send_message(message.from_user.id,'🔐 GOD PANEL — private owner control.',reply_markup=god_menu()); self.bot.reply_to(message,'📩 I sent the GOD PANEL to your private chat.')
                except Exception: log.exception('could not open private GOD panel')
                return
            self.bot.send_message(message.chat.id,'🔐 GOD PANEL\n\nAll admin and automation controls are here.',reply_markup=god_menu())
        register_chaos_admin(self.bot,self.runtime)
        register_owner_controls(self.bot,self.runtime)
        register_moderation(self.bot,self.runtime)
        self.handlers=TelegramHandlers(self.bot,self.runtime)
        self.memory_handlers=MemoryHandlers(self.bot,self.runtime,self.handlers)
        register_smart_archive(self.bot,self.runtime)
        self.media_automation=MediaAutomation(self.bot,self.runtime); self.media_automation.start()
        try:self.handlers._bot_username=(self.bot.get_me().username or '').lower()
        except Exception:self.handlers._bot_username=''; log.exception('Telegram getMe failed')
        install_commands(self.bot); self._configure_webhook(); self._start_proactive()
    def _configure_webhook(self):
        base=settings.public_base_url
        if not base: log.warning('Telegram webhook NOT configured: PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is missing'); return
        url=f'{base.rstrip("/")}/telegram/webhook'
        allowed_updates=['message','edited_message','channel_post','edited_channel_post','callback_query','my_chat_member','chat_member','pre_checkout_query']
        try:
            for attempt in range(3):
                try:
                    self.bot.set_webhook(url=url,secret_token=settings.webhook_secret or None,allowed_updates=allowed_updates,drop_pending_updates=False)
                    break
                except Exception as exc:
                    if '429' not in str(exc) or attempt==2: raise
                    time.sleep(1.5*(attempt+1))
            info=self.bot.get_webhook_info()
            log.info('telegram webhook configured: url=%s pending=%s allowed=%s last_error=%s',url,getattr(info,'pending_update_count',0),allowed_updates,getattr(info,'last_error_message','') or 'none')
        except Exception: log.exception('webhook setup failed; existing webhook will be left untouched')
    def _start_proactive(self):
        if not settings.enabled_proactive:return
        self.scheduler=ProactiveScheduler(self._proactive_tick); self.scheduler.start()
    def _proactive_tick(self):
        chat_ids=list(self.runtime.memory._data.keys())
        if chat_ids:self.handlers.proactive(random.choice(chat_ids))
    def process(self,update): self.bot.process_new_updates([update])
