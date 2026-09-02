from __future__ import annotations

import logging
import random
import threading
import time
from telebot import types
from app.images.pool import ImageRef

log = logging.getLogger(__name__)


class MediaAutomation:
    """Per-group random media sender controlled by group administrators."""

    def __init__(self, bot, runtime):
        self.bot = bot
        self.rt = runtime
        self._stop = threading.Event()
        self._thread = None
        self.register()

    def state(self, chat_id: int) -> dict:
        return self.rt.db.get_json('chat_state', 'chat_id', chat_id, {})

    def save(self, chat_id: int, **changes) -> dict:
        s = self.state(chat_id)
        s.update(changes)
        self.rt.db.save_state(chat_id, s)
        return s

    def _global_defaults(self):
        try:
            root = self.rt.db.get_json('chat_settings', 'chat_id', 0, {})
            d = dict(root.get('media_defaults') or {})
        except Exception:
            d = {}
        d.setdefault('auto_media_enabled', True); d.setdefault('auto_media_interval_min', 120); d.setdefault('auto_media_interval_max', 300)
        d.setdefault('active_media_enabled', True); d.setdefault('auto_media_delete_after_send', False); d.setdefault('media_requests_enabled', True)
        return d

    def _ensure_defaults(self, chat_id: int):
        s = self.state(chat_id); d = self._global_defaults()
        s.setdefault('auto_media_enabled', d['auto_media_enabled']); s.setdefault('auto_text_enabled', False)
        s.setdefault('auto_media_interval_min', d['auto_media_interval_min']); s.setdefault('auto_media_interval_max', d['auto_media_interval_max'])
        s.setdefault('auto_media_delete_after_send', d['auto_media_delete_after_send']); s.setdefault('media_requests_enabled', d['media_requests_enabled'])
        s.setdefault('auto_media_next_at', 0); s.setdefault('auto_text_next_at', 0); s.setdefault('active_media_enabled', d['active_media_enabled'])
        s.setdefault('active_media_min_gap', 20); s.setdefault('active_media_max_gap', 60); s.setdefault('active_media_next_at', 0)
        s.setdefault('recent_auto_media_ids', [])
        # Do not rewrite the state on every 10-second worker tick.
        if not self.state(chat_id):
            self.rt.db.save_state(chat_id, s)
        return s

    def _is_group_admin(self, message) -> bool:
        try:
            chat = getattr(message, 'chat', None); user = getattr(message, 'from_user', None)
            if not chat or not user or getattr(chat, 'type', '') not in ('group', 'supergroup'): return False
            return getattr(self.bot.get_chat_member(chat.id, user.id), 'status', '') in ('creator', 'administrator')
        except Exception: return False

    def _group_keyboard(self, chat_id: int):
        s = self._ensure_defaults(chat_id)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton(f'🖼 Auto Media: {"ON" if s.get("auto_media_enabled") else "OFF"}', callback_data=f'auto:toggle:{chat_id}'),
               types.InlineKeyboardButton(f'⚡ Active Pulse: {"ON" if s.get("active_media_enabled") else "OFF"}', callback_data=f'auto:pulse:{chat_id}'))
        kb.add(types.InlineKeyboardButton('⏱ Interval', callback_data=f'auto:interval:{chat_id}'),
               types.InlineKeyboardButton(f'🗑 Delete: {"ON" if s.get("auto_media_delete_after_send") else "OFF"}', callback_data=f'auto:cleanup:{chat_id}'))
        kb.add(types.InlineKeyboardButton(f'📩 Requests: {"ON" if s.get("media_requests_enabled", True) else "OFF"}', callback_data=f'auto:requests:{chat_id}'))
        kb.add(types.InlineKeyboardButton('🧹 Cleanup used', callback_data=f'auto:cleanup_now:{chat_id}'))
        return kb

    def text(self, chat_id: int) -> str:
        s = self._ensure_defaults(chat_id)
        return ('🤖 AUTO MEDIA\n\n'
                f'Media: {"ON 🟢" if s.get("auto_media_enabled") else "OFF 🔴"}\n'
                f'Active pulse: {"ON 🟢" if s.get("active_media_enabled") else "OFF 🔴"}\n'
                f'Interval: {int(s.get("auto_media_interval_min", 120))}–{int(s.get("auto_media_interval_max", 300))} min\n'
                f'Delete after send: {"ON" if s.get("auto_media_delete_after_send") else "OFF"}\n'
                f'Explicit requests: {"ON 🟢" if s.get("media_requests_enabled", True) else "OFF 🔴"}\n'
                f'Stored media: {self.rt.db.media_count(chat_id)}\n\nغيّر التوقيت بالأمر: /automedia 10 30')

    def _known_group_ids(self):
        ids = set()
        try:
            root = self.rt.db.get_json('chat_settings', 'chat_id', 0, {})
            for x in root.get('known_chats', []):
                try:
                    cid = int(x.get('chat_id'))
                    if cid < 0: ids.add(cid)
                except Exception: pass
        except Exception: pass
        return ids

    def register(self):
        @self.bot.message_handler(commands=['automedia'])
        def automedia_command(m):
            if not self._is_group_admin(m): return
            args = (getattr(m, 'text', '') or '').split()[1:]
            if len(args) == 2:
                try:
                    lo=max(1,min(10080,int(args[0]))); hi=max(lo,min(10080,int(args[1])))
                    self.save(m.chat.id, auto_media_interval_min=lo, auto_media_interval_max=hi, auto_media_next_at=0)
                    self.bot.reply_to(m, f'✅ تم ضبط إرسال الميديا العشوائي كل {lo}–{hi} دقيقة.'); return
                except Exception:
                    self.bot.reply_to(m, '❌ استعمل: /automedia 10 30'); return
            self.bot.send_message(m.chat.id, self.text(m.chat.id), reply_markup=self._group_keyboard(m.chat.id))

        @self.bot.message_handler(content_types=['photo','video','sticker','animation','audio','voice'], func=lambda m: getattr(getattr(m, 'chat', None), 'type', '') in ('group','supergroup'))
        def collect_media(m):
            try:
                kind=getattr(m,'content_type',None); obj=getattr(m,kind,None) if kind else None
                file_id=(obj[-1].file_id if kind=='photo' and obj else getattr(obj,'file_id',None))
                if not file_id: return
                self.rt.images.add(ImageRef(int(m.chat.id),int(m.message_id),file_id,m.date or time.time(),None,int(getattr(m.from_user,'id',0) or 0),kind))
            except Exception: log.exception('media collection failed')

        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('auto:'))
        def callbacks(c):
            try:
                parts=c.data.split(':'); action=parts[1]; chat_id=int(parts[2]) if len(parts)>2 else int(getattr(getattr(c.message,'chat',None),'id',0))
                fake=types.SimpleNamespace(chat=getattr(c.message,'chat',None),from_user=c.from_user)
                if not self._is_group_admin(fake): self.bot.answer_callback_query(c.id,'فقط أدمن الكروب يقدر يتحكم.',show_alert=True); return
                if int(getattr(getattr(c.message,'chat',None),'id',0)) != chat_id: self.bot.answer_callback_query(c.id,'Invalid group.',show_alert=True); return
                if action=='toggle': self.save(chat_id,auto_media_enabled=not bool(self.state(chat_id).get('auto_media_enabled',True)),auto_media_next_at=0)
                elif action=='pulse': self.save(chat_id,active_media_enabled=not bool(self.state(chat_id).get('active_media_enabled',True)),active_media_next_at=0)
                elif action=='cleanup': self.save(chat_id,auto_media_delete_after_send=not bool(self.state(chat_id).get('auto_media_delete_after_send',False)))
                elif action=='requests': self.save(chat_id,media_requests_enabled=not bool(self.state(chat_id).get('media_requests_enabled',True)))
                elif action=='interval': self.bot.answer_callback_query(c.id,'اكتب في الكروب: /automedia 10 30',show_alert=True); return
                elif action=='cleanup_now': n=self.rt.db.delete_used_media(chat_id); self._edit(c,chat_id,f'🧹 Removed {n} used media records.'); return
                self._edit(c,chat_id); self.bot.answer_callback_query(c.id)
            except Exception:
                log.exception('automation callback failed')
                try:self.bot.answer_callback_query(c.id,'Automation error',show_alert=True)
                except Exception:pass

    def _edit(self,c,chat_id,prefix=''):
        body=(prefix+'\n\n' if prefix else '')+self.text(chat_id)
        try:self.bot.edit_message_text(body,c.message.chat.id,c.message.message_id,reply_markup=self._group_keyboard(chat_id))
        except Exception:self.bot.send_message(c.message.chat.id,body,reply_markup=self._group_keyboard(chat_id))

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._thread=threading.Thread(target=self._run,daemon=True,name='merva-auto-send'); self._thread.start()

    def _run(self):
        while not self._stop.wait(15):
            try:self.tick()
            except Exception:log.exception('auto-send tick failed')

    def _send_media(self,chat_id:int,ref:ImageRef)->bool:
        sender={'photo':self.bot.send_photo,'video':self.bot.send_video,'sticker':self.bot.send_sticker,'animation':self.bot.send_animation,'audio':self.bot.send_audio,'voice':self.bot.send_voice}.get(ref.media_type)
        if not sender:return False
        sender(chat_id,ref.telegram_file_id); self.rt.images.mark_used(ref); return True

    def _human_recent(self,chat_id:int,seconds:int=300)->bool:
        try:
            now=time.time(); return any((not x.is_bot) and x.timestamp and now-float(x.timestamp)<=seconds for x in self.rt.memory.recent(chat_id,25))
        except Exception:return False

    def _remember_auto_media(self,s:dict,ref:ImageRef)->None:
        recent=[str(x) for x in (s.get('recent_auto_media_ids') or []) if x]
        recent.append(ref.telegram_file_id)
        s['recent_auto_media_ids']=recent[-5:]

    def _active_pulse(self,chat_id:int,s:dict,now:float)->bool:
        if not bool(s.get('active_media_enabled')) or not bool(s.get('auto_media_enabled')):return False
        if not self._human_recent(chat_id,300) or now<float(s.get('active_media_next_at',0) or 0) or random.random()>0.20:return False
        blocked=set(s.get('recent_auto_media_ids') or [])
        ref=self.rt.images.choose_random_media(chat_id,avoid_file_ids=blocked)
        if not ref:return False
        try:
            if not self._send_media(chat_id,ref):return False
            self._remember_auto_media(s,ref)
            lo=max(20,int(s.get('active_media_min_gap',20)));hi=max(lo,int(s.get('active_media_max_gap',60)))
            self.save(chat_id,active_media_next_at=now+random.randint(lo*60,hi*60),recent_auto_media_ids=s['recent_auto_media_ids'])
            if s.get('auto_media_delete_after_send'):self.rt.images.remove(ref)
            return True
        except Exception:log.exception('active media pulse failed for %s',chat_id);return False

    def _tick_group(self,chat_id:int):
        s=self._ensure_defaults(chat_id)
        if not bool(s.get('auto_media_enabled')):return
        now=time.time()
        if self._active_pulse(chat_id,s,now):return
        if now<float(s.get('auto_media_next_at',0) or 0):return
        lo=max(1,int(s.get('auto_media_interval_min',120)));hi=max(lo,int(s.get('auto_media_interval_max',300)))
        blocked=set(s.get('recent_auto_media_ids') or [])
        ref=self.rt.images.choose_random_media(chat_id,avoid_file_ids=blocked)
        # Schedule first, then send; a failed send won't cause a tight retry loop.
        self.save(chat_id,auto_media_next_at=now+random.randint(lo*60,hi*60))
        if not ref:return
        try:
            if self._send_media(chat_id,ref):
                self._remember_auto_media(s,ref)
                self.save(chat_id,recent_auto_media_ids=s['recent_auto_media_ids'])
                if s.get('auto_media_delete_after_send'):self.rt.images.remove(ref)
        except Exception:log.exception('automatic media send failed for %s',chat_id)

    def tick(self):
        for chat_id in self._known_group_ids():self._tick_group(chat_id)
