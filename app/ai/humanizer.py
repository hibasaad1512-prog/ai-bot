from __future__ import annotations
import random, re
from app.chaos.personality import Personality

EMOJIS = ["😭", "💀", "😹", "👀", "😺", "nah", "lol"]


def humanize(text: str, personality: Personality, style: dict) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip())
    text = text.strip('"')
    text = text[:600].rstrip()
    imp = personality.human_imperfection / 100

    # Keep imperfection subtle: style should feel natural, not corrupted.
    if random.random() < imp * 0.26:
        text = text.lower()
    if random.random() < imp * 0.18:
        text = re.sub(r"[.!?]+$", "", text)
    if random.random() < imp * 0.08 and len(text.split()) >= 6:
        parts = text.split()
        text = " ".join(parts[:-1])
    if random.random() < (personality.emoji / 100) * 0.22 and not re.search(r"[😭💀😹👀😺]", text):
        text = f"{text} {random.choice(EMOJIS[:5])}"
    return text[:600].strip()
