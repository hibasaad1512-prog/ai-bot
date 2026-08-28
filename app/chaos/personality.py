from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
from app.config import settings

FIELDS = ("chaos","humor","social","weirdness","images","events","roast","emoji","human_imperfection","proactivity")

@dataclass(slots=True)
class Personality:
    chaos: int = settings.defaults.chaos
    humor: int = settings.defaults.humor
    social: int = settings.defaults.social
    weirdness: int = settings.defaults.weirdness
    images: int = settings.defaults.images
    events: int = settings.defaults.events
    roast: int = settings.defaults.roast
    emoji: int = settings.defaults.emoji
    human_imperfection: int = settings.defaults.human_imperfection
    proactivity: int = settings.defaults.proactivity

    def to_dict(self) -> dict[str, int]: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Personality":
        return cls(**{f:max(0,min(100,int(data.get(f,getattr(cls(),f))))) for f in FIELDS})
