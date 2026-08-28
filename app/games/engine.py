from __future__ import annotations
import random,time
from dataclasses import dataclass,field
from .points import Points
@dataclass
class Game:
    game_id:str; chat_id:int; kind:str; participants:set[int]=field(default_factory=set); ends_at:float=0
class GameEngine:
    def __init__(self,points:Points):self.points=points; self.games:dict[int,Game]={}
    def start(self,chat_id:int,kind:str,duration:int=60)->Game:
        g=Game(f"{chat_id}:{int(time.time()*1000)}",chat_id,kind,set(),time.time()+duration); self.games[chat_id]=g; return g
    def join(self,chat_id:int,user_id:int)->bool:
        g=self.games.get(chat_id)
        if not g or time.time()>g.ends_at:return False
        g.participants.add(user_id);return True
    def finish(self,chat_id:int):
        g=self.games.pop(chat_id,None)
        if not g or not g.participants:return None
        winner=random.choice(tuple(g.participants)); self.points.award(chat_id,winner,10,True); return winner
