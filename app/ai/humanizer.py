from __future__ import annotations

import random
import re
from app.chaos.personality import Personality


def humanize(text: str, personality: Personality, style: dict) -> str:
    """Light local cleanup only. Never inject random emojis or unrelated text."""
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text.strip()).strip('"')[:600].rstrip()
    if not text:
        return ""

    # Keep the occasional tiny imperfection, but never alter meaning.
    imp = max(0.0, min(1.0, personality.human_imperfection / 100))
    if len(text.split()) >= 12 and random.random() < imp * 0.012:
        text = re.sub(r"[.!?]+$", "", text).rstrip()

    return text[:600].strip()
