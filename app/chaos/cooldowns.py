from __future__ import annotations

import random
import threading
import time
from collections import defaultdict, deque


class CooldownStore:
    """Thread-safe anti-spam state shared by all bot actions."""

    def __init__(self):
        self.until: dict[str, float] = {}
        self.hour: defaultdict[int, deque[float]] = defaultdict(deque)
        self.consecutive: defaultdict[int, int] = defaultdict(int)
        self._lock = threading.RLock()

    def active(self, key: str) -> bool:
        with self._lock:
            return time.time() < self.until.get(key, 0.0)

    def action_active(self, chat_id: int, action: str) -> bool:
        return self.active(f"action:{chat_id}:{action}")

    def set_action(self, chat_id: int, action: str, seconds: float) -> None:
        self.set(f"action:{chat_id}:{action}", seconds)

    def set(self, key: str, seconds: float) -> None:
        with self._lock:
            self.until[key] = time.time() + max(0.0, float(seconds))

    def try_gate(self, chat_id: int, *, global_cooldown: float, hourly_limit: int, max_consecutive: int) -> bool:
        """Reserve a reply slot without counting a reply yet."""
        with self._lock:
            now = time.time()
            self._trim(chat_id)
            if len(self.hour[chat_id]) >= max(1, hourly_limit):
                return False
            if self.consecutive[chat_id] >= max(1, max_consecutive):
                return False
            if now < self.until.get(f"chat:{chat_id}", 0.0):
                return False
            self.until[f"chat:{chat_id}"] = now + max(0.0, float(global_cooldown))
            return True

    def record_action(self, chat_id: int, action: str | None = None) -> None:
        """Commit a successfully sent action to the budgets."""
        with self._lock:
            self.hour[chat_id].append(time.time())
            self._trim(chat_id)
            self.consecutive[chat_id] += 1
            if action:
                self.until[f"last-action:{chat_id}:{action}"] = time.time()

    def record_human_message(self, chat_id: int) -> None:
        with self._lock:
            self.consecutive[chat_id] = 0

    def consecutive_count(self, chat_id: int) -> int:
        with self._lock:
            return self.consecutive[chat_id]

    def hourly_count(self, chat_id: int) -> int:
        with self._lock:
            self._trim(chat_id)
            return len(self.hour[chat_id])

    def claim(self, chat_id: int, action: str, *, action_cooldown: float, global_cooldown: float, hourly_limit: int, max_consecutive: int) -> bool:
        """Atomically reserve a full action, including its counters."""
        with self._lock:
            now = time.time()
            self._trim(chat_id)
            if len(self.hour[chat_id]) >= max(1, hourly_limit):
                return False
            if self.consecutive[chat_id] >= max(1, max_consecutive):
                return False
            if now < self.until.get(f"chat:{chat_id}", 0.0):
                return False
            if now < self.until.get(f"action:{chat_id}:{action}", 0.0):
                return False
            self.until[f"chat:{chat_id}"] = now + max(0.0, global_cooldown)
            self.until[f"action:{chat_id}:{action}"] = now + max(0.0, action_cooldown)
            self.hour[chat_id].append(now)
            self.consecutive[chat_id] += 1
            return True

    def release_global(self, chat_id: int) -> None:
        """Release only a pre-AI reservation."""
        with self._lock:
            self.until.pop(f"chat:{chat_id}", None)

    def _trim(self, chat_id: int) -> None:
        cut = time.time() - 3600.0
        q = self.hour[chat_id]
        while q and q[0] < cut:
            q.popleft()

    @staticmethod
    def random_gap(low: int, high: int) -> float:
        return random.uniform(min(low, high), max(low, high))
