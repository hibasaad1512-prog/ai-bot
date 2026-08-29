from __future__ import annotations

import logging
import random
import time

from app.config import settings
from app.database import Database
from app.memory.context import ContextStore
from app.images.pool import ImagePool
from app.ai.groq import GroqProvider
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

        self.memory = ContextStore(
            settings.memory_size,
            settings.memory_ttl_seconds,
        )

        self.images = ImagePool(
            settings.image_pool_ttl_seconds
        )

        self.ai = GroqProvider()
        self.chaos = ChaosEngine()

        self.games = GameEngine(
            Points(self.db)
        )

        self.moderation = ModerationDetector(
            ModerationPolicy(
                settings.enabled_moderation
            )
        )

        self.personalities: dict[int, Personality] = {}
        self.language_modes: dict[int, str] = {}

        # آخر مرة تم فيها تشغيل proactive لكل شات
        self.last_proactive: dict[int, float] = {}

        # الوقت القادم للرسالة العشوائية لكل شات
        self.next_proactive: dict[int, float] = {}

        # --------------------------------------------------
        # Random proactive interval
        #
        # 6 ساعات = 21600 ثانية
        # 15 ساعة = 54000 ثانية
        #
        # كل شات يحصل على وقت عشوائي مستقل.
        # --------------------------------------------------

        self.proactive_min_seconds = int(
            getattr(
                settings,
                "proactive_min_interval",
                21600,
            )
        )

        self.proactive_max_seconds = int(
            getattr(
                settings,
                "proactive_max_interval",
                54000,
            )
        )

        if self.proactive_max_seconds < self.proactive_min_seconds:
            (
                self.proactive_min_seconds,
                self.proactive_max_seconds,
            ) = (
                self.proactive_max_seconds,
                self.proactive_min_seconds,
            )

    # ======================================================
    # Personality
    # ======================================================

    def personality(
        self,
        chat_id: int,
    ) -> Personality:
        p = self.personalities.get(chat_id)

        if p:
            return p

        data = self.db.get_json(
            "chat_settings",
            "chat_id",
            chat_id,
            {},
        )

        p = Personality.from_dict(
            data.get(
                "personality",
                {},
            )
        )

        self.personalities[chat_id] = p

        return p

    def save_personality(
        self,
        chat_id: int,
        p: Personality,
    ):
        data = self.db.get_json(
            "chat_settings",
            "chat_id",
            chat_id,
            {
                "personality": {}
            },
        )

        data["personality"] = p.to_dict()

        self.db.save_chat_settings(
            chat_id,
            data,
        )

        self.personalities[chat_id] = p

    # ======================================================
    # Language
    # ======================================================

    def get_language_mode(
        self,
        chat_id: int,
    ) -> str:
        if chat_id in self.language_modes:
            return self.language_modes[chat_id]

        data = self.db.get_json(
            "chat_settings",
            "chat_id",
            chat_id,
            {},
        )

        mode = str(
            data.get(
                "language_mode",
                "auto",
            )
        )

        self.language_modes[chat_id] = mode

        return mode

    def save_language_mode(
        self,
        chat_id: int,
        mode: str,
    ) -> None:
        allowed = {
            "auto",
            "en",
            "ar",
            "ar-MA",
            "fr",
            "es",
            "tr",
            "de",
            "it",
            "ja",
            "ko",
            "zh",
        }

        if mode not in allowed:
            mode = "auto"

        data = self.db.get_json(
            "chat_settings",
            "chat_id",
            chat_id,
            {},
        )

        data["language_mode"] = mode

        self.db.save_chat_settings(
            chat_id,
            data,
        )

        self.language_modes[chat_id] = mode

    # ======================================================
    # Proactive scheduler
    # ======================================================

    def schedule_proactive(
        self,
        chat_id: int,
        force: bool = False,
    ) -> float:
        """
        يعطي هذا الشات موعدًا عشوائيًا جديدًا بين 6 و15 ساعة.

        لا يرسل أي شيء بنفسه.
        handlers.py يستدعي proactive() عندما يحين الوقت.
        """

        now = time.time()

        if (
            not force
            and chat_id in self.next_proactive
            and now < self.next_proactive[chat_id]
        ):
            return self.next_proactive[chat_id]

        delay = random.randint(
            self.proactive_min_seconds,
            self.proactive_max_seconds,
        )

        next_time = now + delay

        self.next_proactive[chat_id] = next_time
        self.last_proactive[chat_id] = now

        return next_time

    def proactive_due(
        self,
        chat_id: int,
    ) -> bool:
        """
        هل حان وقت الرسالة العشوائية لهذا الشات؟
        """

        now = time.time()

        if chat_id not in self.next_proactive:
            self.schedule_proactive(chat_id)
            return False

        return now >= self.next_proactive[chat_id]

    def mark_proactive_done(
        self,
        chat_id: int,
    ) -> None:
        """
        بعد إرسال الرسالة، حدد موعدًا عشوائيًا جديدًا.
        """

        now = time.time()

        self.last_proactive[chat_id] = now

        delay = random.randint(
            self.proactive_min_seconds,
            self.proactive_max_seconds,
        )

        self.next_proactive[chat_id] = (
            now + delay
        )

    def proactive_remaining(
        self,
        chat_id: int,
    ) -> int:
        """
        عدد الثواني المتبقية حتى الرسالة العشوائية.
        """

        if chat_id not in self.next_proactive:
            self.schedule_proactive(chat_id)

        return max(
            0,
            int(
                self.next_proactive[chat_id]
                - time.time()
            ),
        )