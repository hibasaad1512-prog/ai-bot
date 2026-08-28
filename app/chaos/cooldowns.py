from __future__ import annotations
import time, random
from collections import defaultdict, deque

class CooldownStore:
    def __init__(self):
        self.until: dict[str,float] = {}; self.hour: defaultdict[int,deque[float]] = defaultdict(deque)
    def active(self, key: str) -> bool: return time.time() < self.until.get(key, 0)
    def action_active(self, chat_id:int, action:str)->bool: return self.active(f"action:{chat_id}:{action}")
    def set_action(self, chat_id:int, action:str, seconds:float)->None: self.set(f"action:{chat_id}:{action}",seconds)
    def set(self, key: str, seconds: float) -> None: self.until[key] = time.time()+seconds
    def record_action(self, chat_id: int) -> None: self.hour[chat_id].append(time.time()); self._trim(chat_id)
    def hourly_count(self, chat_id: int) -> int: self._trim(chat_id); return len(self.hour[chat_id])
    def _trim(self, chat_id: int) -> None:
        cut=time.time()-3600; q=self.hour[chat_id]
        while q and q[0]<cut: q.popleft()
    def random_gap(self, low: int, high: int) -> float: return random.uniform(low, high)
