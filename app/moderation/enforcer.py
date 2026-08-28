from __future__ import annotations
import logging
log=logging.getLogger(__name__)
class ModerationEnforcer:
    def __init__(self,bot):self.bot=bot
    def apply(self,message,action:str,reason:str)->bool:
        try:
            if action=="delete":
                self.bot.delete_message(message.chat.id,message.message_id); return True
            if action=="warn":
                self.bot.reply_to(message,f"easy 😭 ({reason})"); return True
            return False
        except Exception:log.exception("moderation action failed"); return False
