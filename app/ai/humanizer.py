from __future__ import annotations
import random, re
from app.chaos.personality import Personality

# Rare, context-neutral reactions. The model decides whether an emoji belongs;
# this layer only adds a tiny amount of variation when the answer has none.
EMOJIS = ["😹", "👀", "😺", "😭"]

_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")


def humanize(text: str, personality: Personality, style: dict) -> str:
    if not text:
        return ""

    # Never rewrite wording aggressively: coherence is more important than
    # artificial "human imperfections".
    text = re.sub(r"\s+", " ", text.strip()).strip('"')[:600].rstrip()
    if not text:
        return ""

    # Tiny variation only on longer answers. It must never remove content or
    # splice unrelated phrases into the model's answer.
    imp = max(0.0, min(1.0, personality.human_imperfection / 100))
    if len(text.split()) >= 12 and random.random() < imp * 0.025:
        text = re.sub(r"[.!?]+$", "", text).rstrip()

    # Very low probability emoji. Do not add one if the model already used one.
    # Keep emoji attached to a natural sentence end rather than creating noise.
    emoji_level = max(0.0, min(1.0, personality.emoji / 100))
    probability = emoji_level * 0.025
    if (
        random.random() < probability
        and not _EMOJI_RE.search(text)
        and len(text.split()) <= 45
    ):
        text = f"{text} {random.choice(EMOJIS)}"

    return text[:600].strip()
