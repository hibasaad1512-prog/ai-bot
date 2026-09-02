from __future__ import annotations

import logging
import random
import threading
import time
from telebot import types
from app.images.pool import ImageRef
from app.telegram.memory_admin import is_owner

log = logging.getLogger(__name__)
OWNER_ID = 8734853156

class MediaAutomation:
    """Activity-aware random media sender for the single owner-selected group."""
    def __init__(self, bot, runtime):
        self.bot=bot; self.rt=runtime; self._stop=threading.Event(); self._thread=None
        self.register()
    def state(self, chat_id:int)->dict:return self.rt.db.get_json('chat_state','chat_id',chat_id,{})
    def save(self,chat_id:int,**changes)->dict:
        s=self.state(chat_id); s.update(changes); self.rt.db.save_state(chat_id,s); return s
    def _target(self):
        try:
            root=self.rt.db.get_json('chat_settings','chat_id',0,{})
            cid=int(root.get('selected_chat_id',0) or 0)
            if cid < 0:return cid
        except Exception:pass
        try:return int(self.state(OWNER_ID).get('chaos_target_chat_id'))
        except Exception:return None
    def _ensure_defaults(self,chat_id:int):
        s=self.state(chat_id)
        s.setdefault('auto_media_enabled',True); s.setdefault('auto_text_enabled',False)
        s.setdefault('auto_media_interval_min',120); s.setdefault('auto_media_interval_max',300)
        s.setdefault('auto_media_delete_after_send',False); s.setdefault('auto_media_next_at',0); s.setdefault('auto_text_next_at',0)
        s.setdefault('active_media_enabled',True); s.setdefault('active_media_min_gap',20); s.setdefault('active_media_max_gap',60); s.setdefault('active_media_next_at',0)
        self.rt.db.save_state(chat_id,s); return s
    def keyboard(self,chat_id:int):
        s=self._ensure_defaults(chat_id); media=bool(s.get('auto_media_enabled')); text=bool(s.get('auto_text_enabled')); cleanup=bool(s.get('auto_media_delete_after_send')); pulse=bool(s.get('active_media_enabled'))
        kb=types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton(f'🖼 Auto Media: {"ON" if media else "OFF"}',callback_data='auto:toggle'),types.InlineKeyboardButton(f'💬 Auto Text: {"ON" if text else "OFF"}',callback_data='auto:text_toggle'))
        kb.add(types.InlineKeyboardButton(f'⚡ Active Pulse: {"ON" if pulse else "OFF"}',callback_data='auto:pulse_toggle'),types.InlineKeyboardButton(f'🗑 Delete: {"ON" if cleanup else "OFF"}',callback_data='auto:cleanup'))
        kb.add(types.InlineKeyboardButton('⏱ Interval',callback_data='auto:interval'),types.InlineKeyboardButton('🧹 Cleanup used',callback_data='auto:cleanup_now'))
        kb.add(types.InlineKeyboardButton('🖼 Media status',callback_data='auto:status'),types.InlineKeyboardButton('🎯 Choose group',callback_data='mad:chats'))
        kb.add(types.InlineKeyboardButton('⬅️ GOD PANEL',callback_data='owner:back'))
        return kb
    def text(self,chat_id:int)->str:
        s=self._ensure_defaults(chat_id)
        return ('🤖 AUTO SEND\n\n'+f'Media: {"ON 🟢" if s.get("auto_media_enabled") else "OFF 🔴"}\n'+f'Text: {"ON 🟢" if s.get("auto_text_enabled") else "OFF 🔴"}\n'+f'Active pulse: {"ON 🟢" if s.get("active_media_enabled") else "OFF 🔴"}\n'+f'Scheduled interval: {int(s.get("auto_media_interval_min",120))}–{int(s.get("auto_media_interval_max",300))} min\n'+f'Active pulse gap: {int(s.get("active_media_min_gap",20))}–{int(s.get("active_media_max_gap",60))} min\n'+f'Delete media after send: {"ON" if s.get("auto_media_delete_after_send") else "OFF"}\n'+f'Stored media: {self.rt.db.media_count(chat_id)}')
    def register(self):
        @self.bot.message_handler(content_types=['photo','video','sticker','animation','audio','voice'],func=lambda m:getattr(getattr(m,'chat',None),'type','') in ('group','supergroup'))
        def collect_media(m):
            try:
                if m.content_type=='photo':file_id=m.photo[-1].file_id
                elif m.content_type=='video':file_id=m.video.file_id
                elif m.content_type=='sticker':file_id=m.sticker.file_id
                elif m.content_type=='animation':file_id=m.animation.file_id
                elif m.content_type=='audio':file_id=m.audio.file_id
                else:file_id=m.voice.file_id
                self.rt.images.add(ImageRef(int(m.chat.id),int(m.message_id),file_id,time.time(),None,int(getattr(m.from_user,'id',0) or 0),m.content_type))
            except Exception:log.exception('media collection failed')
        @self.bot.callback_query_handler(func=lambda c:bool(c.data) and c.data.startswith('auto:'))
        def callbacks(c):
            if not is_owner(getattr(c.from_user,'id',None)) or getattr(getattr(c.message,'chat',None),'type','')!='private':
                try:self.bot.answer_callback_query(c.id,'Not authorized',show_alert=True)
                except Exception:pass
                return
            action=c.data.split(':',1)[1]; target=self._target()
            try:
                if action=='home':
                    if target:self._edit(c,target)
                    else:self.bot.answer_callback_query(c.id,'Choose a group first',show_alert=True)
                    return
                if action in ('toggle','text_toggle','pulse_toggle','cleanup','interval','cleanup_now','status') and not target:
                    self.bot.answer_callback_query(c.id,'Choose a group first',show_alert=True); return
                if action=='toggle':self.save(target,auto_media_enabled=not bool(self.state(target).get('auto_media_enabled')),auto_media_next_at=0);self._edit(c,target)
                elif action=='text_toggle':self.save(target,auto_text_enabled=not bool(self.state(target).get('auto_text_enabled')),auto_text_next_at=0);self._edit(c,target)
                elif action=='pulse_toggle':self.save(target,active_media_enabled=not bool(self.state(target).get('active_media_enabled')),active_media_next_at=0);self._edit(c,target)
                elif action=='cleanup':self.save(target,auto_media_delete_after_send=not bool(self.state(target).get('auto_media_delete_after_send')));self._edit(c,target)
                elif action=='interval':self.save(OWNER_ID,auto_media_waiting_interval=True,auto_media_interval_target=target);self.bot.send_message(c.message.chat.id,'⏱ Send two numbers in minutes, e.g. 10 30.')
                elif action=='cleanup_now':self._edit(c,target,f'🧹 Removed {self.rt.db.delete_used_media(target)} used media records.')
                elif action=='status':self._edit(c,target)
                self.bot.answer_callback_query(c.id)
            except Exception:
                log.exception('automation callback failed')
                try:self.bot.answer_callback_query(c.id,'Automation error',show_alert=True)
                except Exception:pass
        @self.bot.message_handler(content_types=['text'],func=lambda m:is_owner(getattr(m.from_user,'id',None)) and getattr(m.chat,'type','')=='private' and bool(self.state(OWNER_ID).get('auto_media_waiting_interval')))
        def interval_input(m):
            try:
                p=(m.text or '').split();lo=max(1,min(10080,int(p[0])));hi=max(lo,min(10080,int(p[1])));o=self.state(OWNER_ID);target=int(o['auto_media_interval_target'])
                self.save(target,auto_media_interval_min=lo,auto_media_interval_max=hi,auto_media_next_at=0,auto_text_next_at=0);self.save(OWNER_ID,auto_media_waiting_interval=False,auto_media_interval_target=None);self.bot.send_message(m.chat.id,self.text(target),reply_markup=self.keyboard(target))
            except Exception:self.bot.send_message(m.chat.id,'❌ Use two numbers in minutes, e.g. 10 30.')
    def _edit(self,c,target:int,prefix=''):
        body=(prefix+'\n\n' if prefix else '')+self.text(target)
        try:self.bot.edit_message_text(body,c.message.chat.id,c.message.message_id,reply_markup=self.keyboard(target))
        except Exception:self.bot.send_message(c.message.chat.id,body,reply_markup=self.keyboard(target))
    def start(self):
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self._run,daemon=True,name='merva-auto-send');self._thread.start()
    def _run(self):
        while not self._stop.wait(10):
            try:self.tick()
            except Exception:log.exception('auto-send tick failed')
    def _send_media(self,chat_id:int,ref:ImageRef)->bool:
        if ref.media_type=='photo':self.bot.send_photo(chat_id,ref.telegram_file_id)
        elif ref.media_type=='video':self.bot.send_video(chat_id,ref.telegram_file_id)
        elif ref.media_type=='sticker':self.bot.send_sticker(chat_id,ref.telegram_file_id)
        elif ref.media_type=='animation':self.bot.send_animation(chat_id,ref.telegram_file_id)
        elif ref.media_type=='audio':self.bot.send_audio(chat_id,ref.telegram_file_id)
        elif ref.media_type=='voice':self.bot.send_voice(chat_id,ref.telegram_file_id)
        else:return False
        self.rt.images.mark_used(ref);return True
    def _send_text(self,chat_id:int)->bool:
        try:
            msgs=self.rt.db.recent_messages(chat_id,80);candidates=[m.text.strip() for m in msgs if getattr(m,'text','').strip() and not m.text.startswith('/') and len(m.text.strip())<=160]
            if not candidates:return False
            self.bot.send_message(chat_id,random.choice(candidates));return True
        except Exception:log.exception('automatic text send failed for %s',chat_id);return False
    def _human_recent(self,chat_id:int,seconds:int=300)->bool:
        try:
            recent=self.rt.memory.recent(chat_id,25); now=time.time()
            return any((not x.is_bot) and x.timestamp and now-float(x.timestamp)<=seconds for x in recent)
        except Exception:return False
    def _active_pulse(self,chat_id:int,s:dict,now:float)->bool:
        if not bool(s.get('active_media_enabled')) or not bool(s.get('auto_media_enabled')): return False
        if not self._human_recent(chat_id,300): return False
        if now < float(s.get('active_media_next_at',0) or 0): return False
        if random.random() > 0.20: return False
        ref=self.rt.images.choose_random_media(chat_id)
        if not ref:return False
        try:
            if not self._send_media(chat_id,ref):return False
            if s.get('auto_media_delete_after_send'):self.rt.images.remove(ref)
            lo=max(20,int(s.get('active_media_min_gap',20))); hi=max(lo,int(s.get('active_media_max_gap',60)))
            self.save(chat_id,active_media_next_at=now+random.randint(lo*60,hi*60))
            return True
        except Exception:log.exception('active media pulse failed for %s',chat_id); return False
    def tick(self):
        chat_id=self._target()
        if chat_id is None:return
        s=self._ensure_defaults(chat_id);media_on=bool(s.get('auto_media_enabled'));text_on=bool(s.get('auto_text_enabled'))
        if not(media_on or text_on):return
        now=time.time()
        if self._active_pulse(chat_id,s,now): return
        lo=max(1,int(s.get('auto_media_interval_min',120)));hi=max(lo,int(s.get('auto_media_interval_max',300)))
        if now<float(s.get('auto_media_next_at',0) or 0) and now<float(s.get('auto_text_next_at',0) or 0):return
        next_at=now+random.randint(lo*60,hi*60);self.save(chat_id,auto_media_next_at=next_at,auto_text_next_at=next_at)
        if media_on and text_on:
            ref=self.rt.images.choose_random_media(chat_id)
            if ref and random.random()<0.82:
                try:
                    if self._send_media(chat_id,ref):
                        if s.get('auto_media_delete_after_send'):self.rt.images.remove(ref)
                        return
                except Exception:log.exception('automatic media send failed for %s',chat_id)
            self._send_text(chat_id)
        elif media_on:
            ref=self.rt.images.choose_random_media(chat_id)
            if ref:
                try:
                    if self._send_media(chat_id,ref) and s.get('auto_media_delete_after_send'):self.rt.images.remove(ref)
                except Exception:log.exception('automatic media send failed for %s',chat_id)
        elif text_on:self._send_text(chat_id)
