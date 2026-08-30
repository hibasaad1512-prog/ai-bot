from __future__ import annotations
import random, re
from app.chaos.personality import Personality

EMOJIS = ["😭", "💀", "😹", "👀", "😺"]

def humanize(text: str, personality: Personality, style: dict) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip()).strip('"')[:600].rstrip()
    imp = max(0.0, min(1.0, personality.human_imperfection / 100))

    # Keep variation subtle. Never deliberately corrupt an otherwise coherent answer.
    if len(text.split()) >= 7 and random.random() < imp * 0.10:
        text = re.sub(r"[.!?]+$", "", text)
    if len(text.split()) >= 10 and random.random() < imp * 0.04:
        text = text.replace(" — ", " ", 1)

    # Emoji is flavor, not a requirement. The prompt remains the primary controller.
    emoji_level = max(0.0, min(1.0, personality.emoji / 100))
    probability = emoji_level * 0.08
    if random.random() < probability and not re.search(r"[\U0001F300-\U0001FAFF]", text):
        text = f"{text} {random.choice(EMOJIS)}"

    return text[:600].strip()
