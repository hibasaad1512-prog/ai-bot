from __future__ import annotations

import logging, random, threading, time
from telebot import types
from app.images.pool import ImageRef
from app.telegram.memory_admin import is_owner

log = logging.getLogger(__name__)
OWNER_ID = 8734853156

class MediaAutomation:
    """Persistent per-group automatic media/text sender.

    Telegram file IDs are stored in Neon; binary files stay on Telegram.
    """
    def __init__(self, bot, runtime):
        self.bot = bot; self.rt = runtime; self._stop = threading.Event(); self._thread = None; self.register()

    def state(self, chat_id:int)->dict: return self.rt.db.get_json("chat_state", "chat_id", chat_id, {})
    def save(self, chat_id:int, **changes)->dict:
        s=self.state(chat_id); s.update(changes); self.rt.db.save_state(chat_id,s); return s

    def keyboard(self, chat_id:int):
        s=self.state(chat_id); media=bool(s.get("auto_media_enabled")); text=bool(s.get("auto_text_enabled")); cleanup=bool(s.get("auto_media_delete_after_send"))
        kb=types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton(f"🖼 Auto Media: {'ON' if media else 'OFF'}", callback_data="auto:toggle"), types.InlineKeyboardButton(f"💬 Auto Text: {'ON' if text else 'OFF'}", callback_data="auto:text_toggle"))
        kb.add(types.InlineKeyboardButton(f"🗑 Delete after send: {'ON' if cleanup else 'OFF'}", callback_data="auto:cleanup"))
        kb.add(types.InlineKeyboardButton("⏱ Interval", callback_data="auto:interval"), types.InlineKeyboardButton("🧹 Cleanup used", callback_data="auto:cleanup_now"))
        kb.add(types.InlineKeyboardButton("🖼 Media status", callback_data="auto:status"), types.InlineKeyboardButton("🎯 Choose group", callback_data="mad:chats"))
        kb.add(types.InlineKeyboardButton("⬅️ GOD PANEL", callback_data="mad:god"))
        return kb

    def text(self, chat_id:int)->str:
        s=self.state(chat_id)
        return ("🤖 AUTO SEND\n\n"
                f"Media: {'ON 🟢' if s.get('auto_media_enabled') else 'OFF 🔴'}\n"
                f"Text: {'ON 🟢' if s.get('auto_text_enabled') else 'OFF 🔴'}\n"
                f"Interval: {int(s.get('auto_media_interval_min',60))}–{int(s.get('auto_media_interval_max',180))} minutes\n"
                f"Delete media after send: {'ON' if s.get('auto_media_delete_after_send') else 'OFF'}\n"
                f"Stored media: {self.rt.db.media_count(chat_id)}")

    def register(self):
        @self.bot.message_handler(content_types=["photo","video","sticker","animation"], func=lambda m: getattr(getattr(m,"chat",None),"type","") in ("group","supergroup"))
        def collect_media(m):
            try:
                if m.content_type == "photo": file_id=m.photo[-1].file_id
                elif m.content_type == "video": file_id=m.video.file_id
                elif m.content_type == "sticker": file_id=m.sticker.file_id
                else: file_id=m.animation.file_id
                ref=ImageRef(int(m.chat.id),int(m.message_id),file_id,time.time(),None,int(getattr(m.from_user,"id",0) or 0),m.content_type)
                self.rt.images.add(ref)
            except Exception: log.exception("media collection failed")

        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("auto:"))
        def callbacks(c):
            if not is_owner(getattr(c.from_user,"id",None)) or getattr(getattr(c.message,"chat",None),"type","") != "private":
                try:self.bot.answer_callback_query(c.id,"Not authorized",show_alert=True)
                except Exception:pass
                return
            action=c.data.split(":",1)[1]; target=self._target()
            try:
                if action=="toggle":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    self.save(target,auto_media_enabled=not bool(self.state(target).get("auto_media_enabled")),auto_media_next_at=0); self._edit(c,target)
                elif action=="text_toggle":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    self.save(target,auto_text_enabled=not bool(self.state(target).get("auto_text_enabled")),auto_text_next_at=0); self._edit(c,target)
                elif action=="cleanup":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    self.save(target,auto_media_delete_after_send=not bool(self.state(target).get("auto_media_delete_after_send"))); self._edit(c,target)
                elif action=="interval":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    self.save(OWNER_ID,auto_media_waiting_interval=True,auto_media_interval_target=target); self.bot.send_message(c.message.chat.id,"⏱ Send two numbers in minutes, e.g. 30 120.")
                elif action=="cleanup_now":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    removed=self.rt.db.delete_used_media(target); self._edit(c,target,f"🧹 Removed {removed} used media records.")
                elif action=="status":
                    if not target:return self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True)
                    self._edit(c,target)
                self.bot.answer_callback_query(c.id)
            except Exception:
                log.exception("automation callback failed")
                try:self.bot.answer_callback_query(c.id,"Automation error",show_alert=True)
                except Exception:pass

        @self.bot.message_handler(content_types=["text"],func=lambda m:is_owner(getattr(m.from_user,"id",None)) and getattr(m.chat,"type","")=="private" and bool(self.state(OWNER_ID).get("auto_media_waiting_interval")))
        def interval_input(m):
            try:
                p=(m.text or "").split(); lo=max(1,min(10080,int(p[0]))); hi=max(lo,min(10080,int(p[1])))
                o=self.state(OWNER_ID); target=int(o["auto_media_interval_target"])
                self.save(target,auto_media_interval_min=lo,auto_media_interval_max=hi,auto_media_next_at=0,auto_text_next_at=0)
                self.save(OWNER_ID,auto_media_waiting_interval=False,auto_media_interval_target=None)
                self.bot.send_message(m.chat.id,self.text(target),reply_markup=self.keyboard(target))
            except Exception:self.bot.send_message(m.chat.id,"❌ Use two numbers in minutes, e.g. 30 120.")

    def _target(self):
        try:return int(self.state(OWNER_ID).get("chaos_target_chat_id"))
        except Exception:return None

    def _edit(self,c,target:int,prefix=""):
        body=(prefix+"\n\n" if prefix else "")+self.text(target)
        try:self.bot.edit_message_text(body,c.message.chat.id,c.message.message_id,reply_markup=self.keyboard(target))
        except Exception:self.bot.send_message(c.message.chat.id,body,reply_markup=self.keyboard(target))

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self._run,daemon=True,name="merva-auto-send"); self._thread.start()
    def _run(self):
        while not self._stop.wait(30):
            try:self.tick()
            except Exception:log.exception("auto-send tick failed")

    def tick(self):
        now=time.time()
        for chat_id in self.rt.db.list_chat_ids():
            s=self.state(chat_id); media_on=bool(s.get("auto_media_enabled")); text_on=bool(s.get("auto_text_enabled"))
            if not (media_on or text_on):continue
            lo=max(1,int(s.get("auto_media_interval_min",60))); hi=max(lo,int(s.get("auto_media_interval_max",180)))
            if now >= float(s.get("auto_media_next_at",0) or 0):
                self.save(chat_id,auto_media_next_at=now+random.randint(lo*60,hi*60))
                if media_on:
                    ref=self.rt.images.choose_random_media(chat_id)
                    if ref:
                        try:
                            if ref.media_type=="photo":self.bot.send_photo(chat_id,ref.telegram_file_id)
                            elif ref.media_type=="video":self.bot.send_video(chat_id,ref.telegram_file_id)
                            elif ref.media_type=="sticker":self.bot.send_sticker(chat_id,ref.telegram_file_id)
                            elif ref.media_type=="animation":self.bot.send_animation(chat_id,ref.telegram_file_id)
                            self.rt.images.mark_used(ref)
                            if s.get("auto_media_delete_after_send"):self.rt.images.remove(ref)
                        except Exception:log.exception("automatic media send failed for %s",chat_id)
            if text_on and now >= float(s.get("auto_text_next_at",0) or 0):
                self.save(chat_id,auto_text_next_at=now+random.randint(lo*60,hi*60))
                try:
                    msgs=self.rt.db.recent_messages(chat_id,60); candidates=[m.text.strip() for m in msgs if getattr(m,"text","").strip() and not m.text.startswith("/") and len(m.text.strip())<=160]
                    if candidates:self.bot.send_message(chat_id,random.choice(candidates))
                except Exception:log.exception("automatic text send failed for %s",chat_id)
