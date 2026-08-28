from __future__ import annotations
import logging, random, time
from io import BytesIO
from app.models import ChatMessage
from app.config import settings
from app.ai.dialect import detect
from app.ai.prompts import decision_prompt,response_prompt
from app.ai.humanizer import humanize
from app.ai.schemas import DecisionPayload
from app.chaos.actions import Action, DEFAULT_ACTIONS
from app.telegram.permissions import is_global_admin, is_group, can_use_settings, can_use_testai, can_use_settings_callback
from app.telegram.admin_panel import panel, adjust_panel, language_panel
from app.images.pool import ImageRef
from app.images.collage import side_by_side, collage
from app.images.meme import caption_meme
from app.chaos.social import analyze

log=logging.getLogger(__name__)

class TelegramHandlers:
    def __init__(self,bot,runtime):
        self.bot=bot; self.rt=runtime
        self._register()
    def _register(self):
        from telebot import types
        @self.bot.message_handler(commands=["start"])
        def start(m):
            if is_group(m.chat.type): self.bot.reply_to(m,"i'm here. don't expect me to answer everything 😭")
            else:self.bot.send_message(m.chat.id,"drop me in a group, then /start there")
        @self.bot.message_handler(commands=["testai"])
        def testai(m):
            if not can_use_testai(self.bot, m):return
            lines=["KYOOS AI TEST",f"Gemini {'✅' if self.rt.ai.enabled else '❌'}"]
            try:
                if self.rt.ai.enabled:
                    t=self.rt.ai.generate_text("Reply with exactly: ping")
                    lines.append(f"Text {'✅' if t else '❌'}")
                    d=self.rt.ai.generate_structured("Return should_act=false, action=IGNORE, confidence=0.1, target_message_id=null, language=en, dialect=null, intensity=low.",{})
                    DecisionPayload.validate(d,set()); lines.append("Structured JSON ✅")
                else: lines += ["Text ❌","Structured JSON ❌"]
            except Exception: lines += ["Text/structured ❌"]
            if self.rt.ai.enabled:
                try:
                    from PIL import Image
                    from io import BytesIO
                    b=BytesIO(); Image.new("RGB",(2,2),(0,0,0)).save(b,"JPEG"); _=self.rt.ai.analyze_image(b.getvalue(),"Describe this tiny test image in one word."); lines.append("Vision ✅")
                except Exception:
                    lines.append("Vision ❌")
            else: lines.append("Vision ❌")
            lines.append("Image generation ✅/quota-dependent")
            self.bot.send_message(m.chat.id,"\n".join(lines))
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("panel:") or c.data.startswith("set:") or c.data.startswith("language:"))
        def callbacks(c):
            if not can_use_settings_callback(self.bot, c):
                self.bot.answer_callback_query(c.id, "group admins only", show_alert=True)
                return
            chat_id=c.message.chat.id; p=self.rt.personality(chat_id); data=c.data
            try:
                if data=="panel:back":self.bot.edit_message_text("KYOOS settings",chat_id,c.message.message_id,reply_markup=panel(p, self.rt.get_language_mode(chat_id)))
                elif data=="language:show":self.bot.edit_message_reply_markup(chat_id,c.message.message_id,reply_markup=language_panel(self.rt.get_language_mode(chat_id)))
                elif data.startswith("language:set:"):
                    mode=data.split(":",2)[2]
                    self.rt.save_language_mode(chat_id, mode)
                    self.bot.edit_message_text("KYOOS settings",chat_id,c.message.message_id,reply_markup=panel(p, mode))
                elif data.startswith("set:"):
                    _,key,delta=data.split(":")
                    if delta=="show":self.bot.edit_message_reply_markup(chat_id,c.message.message_id,reply_markup=adjust_panel(p,key))
                    else:
                        value=max(0,min(100,getattr(p,key)+int(delta))); setattr(p,key,value); self.rt.save_personality(chat_id,p); self.bot.edit_message_reply_markup(chat_id,c.message.message_id,reply_markup=adjust_panel(p,key))
            finally:self.bot.answer_callback_query(c.id)
    def admin_command(self,m):
        if not can_use_settings(self.bot, m):
            return
        self.bot.send_message(m.chat.id,"KYOOS settings",reply_markup=panel(self.rt.personality(m.chat.id), self.rt.get_language_mode(m.chat.id)))
    def on_message(self,m):
        if not is_group(m.chat.type) or not m.from_user:return
        text=m.text or m.caption or ""
        image_file_id=None; media_type=None
        if m.photo:
            media_type="photo"; image_file_id=m.photo[-1].file_id
            self.rt.images.add(ImageRef(m.chat.id,m.message_id,image_file_id,time.time(),None,m.from_user.id,"photo"))
        cm=ChatMessage(m.chat.id,m.message_id,m.from_user.id,m.from_user.first_name or m.from_user.username or "user",m.date or time.time(),text,m.reply_to_message.message_id if m.reply_to_message else None,media_type,image_file_id,bool(getattr(m.from_user,"is_bot",False)))
        self.rt.memory.add(cm)
        mod=self.rt.moderation.detect(text,[x.text for x in self.rt.memory.recent(m.chat.id,12) if x.text]) if text else None
        if mod and settings.enabled_moderation and mod.action=="delete":
            try:self.bot.delete_message(m.chat.id,m.message_id)
            except Exception:pass
            return
        personality=self.rt.personality(m.chat.id); recent=self.rt.memory.recent(m.chat.id,40)
        bot_username=getattr(self, "_bot_username", "")
        mentioned=bool(bot_username and f"@{bot_username}".lower() in text.lower()) if text else False
        reply_to_bot=bool(m.reply_to_message and getattr(m.reply_to_message.from_user,"is_bot",False))
        image_opp=1.0 if image_file_id else (0.65 if self.rt.images.choose(m.chat.id) else 0.0)
        decision=self.rt.chaos.decide(m.chat.id,recent,personality,mentioned,reply_to_bot,image_opp,0.25,0.7 if len(text)>20 else 0.4,0.2,0.4,bot_username=bot_username)
        if not decision.should_act or not self.rt.ai.enabled or decision.action==Action.IGNORE:return
        context=self.rt.memory.text(m.chat.id,20)
        lang=detect([x.text for x in recent if x.text])
        signals=decision.signals or analyze(recent,bot_username=bot_username)
        try:
            # Persist only compact language style state, not full chat content.
            state=self.rt.db.get_json("chat_settings","chat_id",m.chat.id,{})
            state["language"]=lang.as_dict(); self.rt.db.save_chat_settings(m.chat.id,state)
            ai_dec=self.rt.ai.generate_structured(decision_prompt(context,personality,lang,[a.value for a in DEFAULT_ACTIONS],signals.as_dict()),{})
            valid={x.message_id for x in recent}; parsed=DecisionPayload.validate(ai_dec,valid)
            if not parsed.should_act:return
            action=parsed.action
            spec=DEFAULT_ACTIONS.get(action)
            if not spec or decision.score < spec.min_score:return
            if self.rt.chaos.cooldowns.action_active(m.chat.id, action.value):return
            if self.rt.chaos.cooldowns.hourly_count(m.chat.id) >= settings.hard_hourly_limit:return
            if action==Action.GENERATE_IMAGE and personality.images < 30:return
            self.execute(m,action,context,lang,parsed.target_message_id,signals.as_dict())
        except Exception:log.exception("AI decision/action failed")
    def proactive(self, chat_id:int):
        recent=self.rt.memory.recent(chat_id,40)
        if not recent:return
        p=self.rt.personality(chat_id)
        now=time.time(); last=recent[-1].timestamp
        if now-last < settings.proactive_quiet_seconds:return
        if p.proactivity < 25:return
        if not self.rt.ai.enabled:return
        if self.rt.chaos.cooldowns.active(f"chat:{chat_id}"):return
        if self.rt.chaos.cooldowns.hourly_count(chat_id) >= settings.soft_hourly_limit:return
        context=self.rt.memory.text(chat_id,20); lang=detect([x.text for x in recent if x.text]); signals=analyze(recent)
        try:
            txt=self.rt.ai.generate_text(response_prompt(context,lang,p,"PROACTIVE",signals=analyze(recent).as_dict()))
            txt=humanize(txt,p,lang.as_dict())
            if txt:
                self.bot.send_message(chat_id,txt[:1000])
                self._record_success(chat_id,"PROACTIVE")
        except Exception:log.exception("proactive action failed")

    def _record_success(self,chat_id:int,action_name:str):
        self.rt.chaos.cooldowns.record_action(chat_id)
        spec=next((s for a,s in DEFAULT_ACTIONS.items() if a.value==action_name),None)
        seconds=spec.cooldown if spec else self.rt.chaos.cooldowns.random_gap(settings.min_cooldown_seconds,settings.max_cooldown_seconds)
        self.rt.chaos.cooldowns.set(f"chat:{chat_id}",seconds)
        self.rt.chaos.cooldowns.set_action(chat_id,action_name,seconds)

    def _companion_send(self,chat_id:int,context:str,lang,p):
        if not settings.companion_bot_tokens:return
        try:
            import telebot
            token=random.choice(settings.companion_bot_tokens); companion=telebot.TeleBot(token,parse_mode=None)
            txt=self.rt.ai.generate_text(response_prompt(context,lang,p,"COMPANION_BOT"))
            if txt: companion.send_message(chat_id,humanize(txt,p,lang.as_dict())[:1000]); self._record_success(chat_id,"COMPANION_BOT")
        except Exception:log.exception("companion bot action failed")

    def execute(self,m,action,context,lang,target_id,signals=None):
        p=self.rt.personality(m.chat.id); reply_id=target_id or m.message_id
        if action in {Action.REPLY_CONTEXT,Action.JOIN_CONVERSATION,Action.CHAOS_TEXT,Action.RANDOM_QUESTION,Action.MINI_CHALLENGE,Action.QUOTE_REMIX,Action.TOPIC_CALLBACK,Action.FAKE_ANNOUNCEMENT,Action.RANDOM_TEMPLATE}:
            focus = next((x for x in self.rt.memory.recent(m.chat.id,40) if x.message_id == target_id), None)
            focus_text = f"{focus.display_name}: {focus.text}" if focus and focus.text else ""
            txt=self.rt.ai.generate_text(response_prompt(context,lang,p,action.value,target=focus_text,signals=signals)); txt=humanize(txt,p,lang.as_dict()); self.bot.send_message(m.chat.id,txt[:1000],reply_to_message_id=reply_id,allow_sending_without_reply=True); self._record_success(m.chat.id,action.value)
        elif action==Action.RANDOM_IMAGE or action==Action.IMAGE_CAPTION or action==Action.CONTEXT_MEME:
            ref=self.rt.images.choose(m.chat.id)
            if not ref:return
            try:
                info=self.bot.get_file(ref.telegram_file_id); raw=self.bot.download_file(info.file_path)
                caption=self.rt.ai.generate_text(response_prompt(context,lang,p,action.value)); caption=humanize(caption,p,lang.as_dict())
                if action==Action.CONTEXT_MEME:out=caption_meme(raw,caption); self.bot.send_photo(m.chat.id,out,caption=None,reply_to_message_id=reply_id)
                else:self.bot.send_photo(m.chat.id,BytesIO(raw),caption=caption[:1024],reply_to_message_id=reply_id)
                self.rt.images.mark_used(ref); self._record_success(m.chat.id,action.value)
            except Exception:log.exception("image action failed")
        elif action in {Action.IMAGE_MASHUP,Action.COLLAGE}:
            a=self.rt.images.choose(m.chat.id); b=self.rt.images.choose(m.chat.id)
            if not a or not b or a.message_id==b.message_id:return
            try:
                raw_a=self.bot.download_file(self.bot.get_file(a.telegram_file_id).file_path); raw_b=self.bot.download_file(self.bot.get_file(b.telegram_file_id).file_path)
                out=side_by_side(raw_a,raw_b) if action==Action.IMAGE_MASHUP else collage([raw_a,raw_b]); self.bot.send_photo(m.chat.id,out,reply_to_message_id=reply_id); self.rt.images.mark_used(a); self.rt.images.mark_used(b); self._record_success(m.chat.id,action.value)
            except Exception:log.exception("mashup failed")
        elif action==Action.REACTION:
            try:
                emoji=random.choice(["👍","😂","❤️","🔥","👀"])
                if hasattr(self.bot,"set_message_reaction"):
                    from telebot.types import ReactionTypeEmoji
                    self.bot.set_message_reaction(m.chat.id,reply_id,[ReactionTypeEmoji(emoji=emoji)])
                else:
                    self.bot.reply_to(m,emoji)
                self._record_success(m.chat.id,action.value)
            except Exception:log.exception("reaction failed")
        elif action==Action.POLL:
            try:
                question=self.rt.ai.generate_text(response_prompt(context,lang,p,"POLL")) or "which one"
                self.bot.send_poll(m.chat.id,question[:300],["yes","no","idk"],is_anonymous=True)
                self._record_success(m.chat.id,action.value)
            except Exception:log.exception("poll failed")
        elif action in {Action.OLD_MESSAGE_REACT,Action.TOPIC_CALLBACK}:
            target=next((x for x in reversed(self.rt.memory.recent(m.chat.id,40)) if x.message_id==target_id),None)
            if not target:return
            txt=self.rt.ai.generate_text(response_prompt(f"Old message: {target.display_name}: {target.text}",lang,p,action.value,target=target.text,signals=signals)); txt=humanize(txt,p,lang.as_dict())
            if txt:self.bot.send_message(m.chat.id,txt[:1000],reply_to_message_id=target.message_id,allow_sending_without_reply=True); self._record_success(m.chat.id,action.value)
        elif action==Action.RANDOM_MEMBER_INTERACTION:
            candidates=[x for x in self.rt.memory.recent(m.chat.id,40) if not x.is_bot and x.user_id!=m.from_user.id]
            if not candidates:return
            target=random.choice(candidates); txt=self.rt.ai.generate_text(response_prompt(f"Talk to {target.display_name}. Context:\n{context}",lang,p,action.value,target=target.display_name,signals=signals)); txt=humanize(txt,p,lang.as_dict())
            if txt:self.bot.send_message(m.chat.id,f"{target.display_name} {txt[:900]}"); self._record_success(m.chat.id,action.value)
        elif action==Action.COMPANION_BOT:
            self._companion_send(m.chat.id,context,lang,p)
        elif action in {Action.STICKER_REACTION}:
            return
        elif action==Action.GENERATE_IMAGE:
            raw=self.rt.ai.generate_image(self.rt.ai.generate_text(response_prompt(context,lang,p,"GENERATE_IMAGE")))
            if raw:self.bot.send_photo(m.chat.id,BytesIO(raw),reply_to_message_id=reply_id); self._record_success(m.chat.id,action.value)
            else:self.bot.send_message(m.chat.id,humanize(self.rt.ai.generate_text(response_prompt(context,lang,p,"CHAOS_TEXT")),p,lang.as_dict()))
        elif action==Action.CHAOS_EVENT:
            g=self.rt.games.start(m.chat.id,random.choice(["emoji","guess","challenge"])); self.bot.send_message(m.chat.id,f"CHAOS EVENT — {g.kind}\nreply JOIN to enter. 60s"); self._record_success(m.chat.id,action.value)
