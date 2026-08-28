from __future__ import annotations
from app.database.db import Database
class Points:
    def __init__(self,db:Database):self.db=db
    def award(self,chat_id:int,user_id:int,delta:int,win:bool=False):return self.db.add_points(chat_id,user_id,delta,win,True)
