from __future__ import annotations

import logging
import random
import time

from app.config import settings
from app.database import Database
from app.memory.context import ContextStore
from app.images.pool import ImagePool
from app.ai.router import MultiProvider
from app.ai.self_learning import SelfLearningMemory
from app.chaos.engine import ChaosEngine
from app.chaos.personality import Personality
from app.games.engine import GameEngine
from app.games.points import Points
from app.moderation.detector import ModerationDetector
from app.moderation.rules import ModerationPolicy

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self):
        self.db = Database(settings.database_url)
        self.memory = ContextStore(settings.memory_size, settings.memory_ttl_seconds, db=self.db)
        self.images = ImagePool(settings.image_pool_ttl_seconds)
        # Every provider shares the same AI interface, prompts/context and Neon-backed memory.
        self.ai = MultiProvider(self.db)
        self.learning = SelfLearningMemory()
        self.chaos = ChaosEngine()
        self.games = GameEngine(Points(self.db))
        self.moderation = ModerationDetector(ModerationPolicy(settings.enabled_moderation))
        self.personalities: dict[int, Personality] = {}
        self.language_modes: dict[int, str] = {}
        self.last_proactive: dict[int, float] = {}
        self.next_proactive: dict[int, float] = {}
        self.proactive_min_seconds = int(getattr(settings, "proactive_min_interval", 21600))
        self.proactive_max_seconds = int(getattr(settings, "proactive_max_interval", 54000))
        if self.proactive_max_seconds < self.proactive_min_seconds:
            self.proactive_min_seconds, self.proactive_max_seconds = self.proactive_max_seconds, self.proactive_min_seconds

    def personality(self, chat_id: int) -> Personality:
        p = self.personalities.get(chat_id)
        if p: return p
        data = self.db.get_json("chat_settings", "chat_id", chat_id, {})
        p = Personality.from_dict(data.get("personality", {}))
        self.personalities[chat_id] = p
        return p

    def save_personality(self, chat_id: int, p: Personality):
        data = self.db.get_json("chat_settings", "chat_id", chat_id, {"personality": {}})
        data["personality"] = p.to_dict()
        self.db.save_chat_settings(chat_id, data)
        self.personalities[chat_id] = p

    def get_language_mode(self, chat_id: int) -> str:
        if chat_id in self.language_modes: return self.language_modes[chat_id]
        data = self.db.get_json("chat_settings", "chat_id", chat_id, {})
        mode = str(data.get("language_mode", "auto"))
        self.language_modes[chat_id] = mode
        return mode

    def save_language_mode(self, chat_id: int, mode: str) -> None:
        allowed = {"auto", "en", "ar", "ar-MA", "fr", "es", "tr", "de", "it", "ja", "ko", "zh"}
        if mode not in allowed: mode = "auto"
        data = self.db.get_json("chat_settings", "chat_id", chat_id, {})
        data["language_mode"] = mode
        self.db.save_chat_settings(chat_id, data)
        self.language_modes[chat_id] = mode

    def schedule_proactive(self, chat_id: int, force: bool = False) -> float:
        now = time.time()
        if not force and chat_id in self.next_proactive and now < self.next_proactive[chat_id]: return self.next_proactive[chat_id]
        next_time = now + random.randint(self.proactive_min_seconds, self.proactive_max_seconds)
        self.next_proactive[chat_id] = next_time
        self.last_proactive[chat_id] = now
        return next_time

    def proactive_due(self, chat_id: int) -> bool:
        if chat_id not in self.next_proactive:
            self.schedule_proactive(chat_id)
            return False
        return time.time() >= self.next_proactive[chat_id]

    def mark_proactive_done(self, chat_id: int) -> None:
        now = time.time()
        self.last_proactive[chat_id] = now
        self.next_proactive[chat_id] = now + random.randint(self.proactive_min_seconds, self.proactive_max_seconds)

    def proactive_remaining(self, chat_id: int) -> int:
        if chat_id not in self.next_proactive: self.schedule_proactive(chat_id)
        return max(0, int(self.next_proactive[chat_id] - time.time()))
