from __future__ import annotations

import logging
import random
import threading
import time
from telebot import types
from app.telegram.memory_admin import is_owner

log=logging.getLogger(__name__)
OWNER_ID=8734853156

class MediaAutomation:
    def __init__(self,bot,runtime):
        self.bot=bot; self.rt=runtime; self._stop=threading.Event(); self._thread=None; self.register()

    def state(self,chat_id:int)->dict: return self.rt.db.get_json("chat_state","chat_id",chat_id,{})
    def save(self,chat_id:int,**changes)->dict:
        s=self.state(chat_id); s.update(changes); self.rt.db.save_state(chat_id,s); return s

    def keyboard(self,chat_id:int):
        s=self.state(chat_id); enabled=bool(s.get("auto_media_enabled",False)); cleanup=bool(s.get("auto_media_delete_after_send",False))
        kb=types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton(f"🤖 Auto Media: {'ON' if enabled else 'OFF'}",callback_data="auto:toggle"))
        kb.add(types.InlineKeyboardButton(f"🗑 Delete after send: {'ON' if cleanup else 'OFF'}",callback_data="auto:cleanup"))
        kb.add(types.InlineKeyboardButton("⏱ Interval",callback_data="auto:interval"),types.InlineKeyboardButton("🧹 Cleanup used",callback_data="auto:cleanup_now"))
        kb.add(types.InlineKeyboardButton("🖼 Media status",callback_data="auto:status"),types.InlineKeyboardButton("🎯 Choose group",callback_data="mad:chats"))
        kb.add(types.InlineKeyboardButton("⬅️ GOD PANEL",callback_data="mad:god"))
        return kb

    def text(self,chat_id:int)->str:
        s=self.state(chat_id)
        return ("🤖 AUTO MEDIA\n\n" f"Status: {'ON 🟢' if s.get('auto_media_enabled') else 'OFF 🔴'}\n"
                f"Interval: {int(s.get('auto_media_interval_min',60))}–{int(s.get('auto_media_interval_max',180))} minutes\n"
                f"Delete after send: {'ON' if s.get('auto_media_delete_after_send') else 'OFF'}\n"
                f"Stored media: {self.rt.db.media_count(chat_id)}\n\n"
                "Each group has its own media pool. PostgreSQL stores Telegram file IDs and metadata only.")

    def register(self):
        @self.bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("auto:"))
        def callbacks(c):
            if not is_owner(getattr(c.from_user,"id",None)) or getattr(c.message.chat,"type","")!="private":
                try:self.bot.answer_callback_query(c.id,"Not authorized",show_alert=True)
                except Exception:pass
                return
            action=c.data.split(":",1)[1]
            try:
                if action=="home":
                    target=self._target()
                    if not target: self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True); return
                    self._edit(c,target); self.bot.answer_callback_query(c.id); return
                target=self._target()
                if not target: self.bot.answer_callback_query(c.id,"Choose a group first",show_alert=True); return
                if action=="toggle":
                    enabled=not bool(self.state(target).get("auto_media_enabled",False)); self.save(target,auto_media_enabled=enabled,auto_media_next_at=0); self._edit(c,target)
                elif action=="cleanup":
                    value=not bool(self.state(target).get("auto_media_delete_after_send",False)); self.save(target,auto_media_delete_after_send=value); self._edit(c,target)
                elif action=="interval":
                    self.save(OWNER_ID,auto_media_waiting_interval=True,auto_media_interval_target=target); self._edit(c,target,"⏱ Send two numbers in this private chat, e.g. `30 120` for 30–120 minutes.")
                elif action=="cleanup_now":
                    removed=self.rt.db.delete_used_media(target); self._edit(c,target,f"🧹 Removed {removed} used media records.")
                elif action=="status": self._edit(c,target)
                self.bot.answer_callback_query(c.id)
            except Exception:
                log.exception("automation callback failed")
                try:self.bot.answer_callback_query(c.id,"Automation error",show_alert=True)
                except Exception:pass

        @self.bot.message_handler(content_types=["text"],func=lambda m:is_owner(getattr(m.from_user,"id",None)) and getattr(m.chat,"type","")=="private" and bool(self.state(OWNER_ID).get("auto_media_waiting_interval")))
        def interval_input(m):
            try:
                parts=(m.text or "").split()
                if len(parts)!=2: raise ValueError
                lo=max(1,min(10080,int(parts[0]))); hi=max(lo,min(10080,int(parts[1])))
                owner_state=self.state(OWNER_ID); target=int(owner_state.get("auto_media_interval_target"))
                self.save(target,auto_media_interval_min=lo,auto_media_interval_max=hi,auto_media_next_at=0)
                self.save(OWNER_ID,auto_media_waiting_interval=False,auto_media_interval_target=None)
                self.bot.send_message(m.chat.id,self.text(target),reply_markup=self.keyboard(target))
            except Exception:
                self.bot.send_message(m.chat.id,"❌ Use two numbers in minutes, e.g. `30 120`.")

    def _target(self):
        s=self.state(OWNER_ID)
        try:return int(s.get("chaos_target_chat_id"))
        except Exception:return None

    def _edit(self,c,target:int,prefix:str=""):
        text=(prefix+"\n\n" if prefix else "")+self.text(target)
        try:self.bot.edit_message_text(text,c.message.chat.id,c.message.message_id,reply_markup=self.keyboard(target))
        except Exception:self.bot.send_message(c.message.chat.id,text,reply_markup=self.keyboard(target))

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self._run,daemon=True,name="merva-media-automation"); self._thread.start()
    def _run(self):
        while not self._stop.wait(45):
            try:self.tick()
            except Exception:log.exception("media automation tick failed")

    def tick(self):
        now=time.time()
        for chat_id in self.rt.db.list_chat_ids():
            s=self.state(chat_id)
            if not s.get("auto_media_enabled"):continue
            next_at=float(s.get("auto_media_next_at",0) or 0)
            if now<next_at:continue
            lo=max(1,int(s.get("auto_media_interval_min",60))); hi=max(lo,int(s.get("auto_media_interval_max",180)))
            self.save(chat_id,auto_media_next_at=now+random.randint(lo*60,hi*60))
            ref=self.rt.images.choose_random_media(chat_id)
            if not ref:continue
            try:
                if ref.media_type=="photo":self.bot.send_photo(chat_id,ref.telegram_file_id)
                elif ref.media_type=="video":self.bot.send_video(chat_id,ref.telegram_file_id)
                elif ref.media_type=="sticker":self.bot.send_sticker(chat_id,ref.telegram_file_id)
                else:continue
                self.rt.images.mark_used(ref)
                if s.get("auto_media_delete_after_send"):self.rt.images.remove(ref)
            except Exception:log.exception("automatic media send failed for %s",chat_id)
