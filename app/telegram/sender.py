from __future__ import annotations
from io import BytesIO
from typing import Any

class Sender:
    def __init__(self,bot):self.bot=bot
    def text(self,chat_id:int,text:str,reply_to:int|None=None):
        kwargs={}
        if reply_to:kwargs["reply_to_message_id"]=reply_to; kwargs["allow_sending_without_reply"]=True
        return self.bot.send_message(chat_id,text[:4000],**kwargs)
    def image(self,chat_id:int,data:BytesIO|bytes,caption:str|None=None,reply_to:int|None=None):
        if isinstance(data,bytes):
            f=BytesIO(data); f.name="kyoos.jpg"; data=f
        kwargs={"caption":caption[:1024] if caption else None}
        if reply_to:kwargs["reply_to_message_id"]=reply_to; kwargs["allow_sending_without_reply"]=True
        return self.bot.send_photo(chat_id,data,**kwargs)
