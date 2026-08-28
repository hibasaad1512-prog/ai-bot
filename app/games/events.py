from __future__ import annotations
from .engine import GameEngine
class ChaosEvents:
    def __init__(self,engine:GameEngine):self.engine=engine
    def create(self,chat_id:int,kind:str="mini_challenge"):return self.engine.start(chat_id,kind)
