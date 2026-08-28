from __future__ import annotations
from dataclasses import dataclass
import re, time
from app.models import ChatMessage
from .scoring import Activity, activity_state

LAUGHTER = re.compile(r"\b(lol|lmao|lmfao|mdr|ptdr|ahaha|haha|xd|😭|😂|💀)\b", re.I)
QUESTION = re.compile(r"[?؟]|\b(why|what|how|who|when|where|pourquoi|quoi|comment|شنو|علاش|كيفاش|واش|علاش|ليش|كيف)\b", re.I)
SERIOUS = re.compile(r"\b(emergency|urgent|help|problem|issue|danger|sad|sorry|condolences|الله يرحمو|تعازي|مشكل|مشكلة|مستعجل|خطر)\b", re.I)

@dataclass(slots=True)
class SocialSignals:
    activity: Activity
    direct_address: bool = False
    reply_to_bot: bool = False
    question: bool = False
    funny: float = 0.0
    serious: float = 0.0
    continuity: float = 0.0
    callback_candidate: bool = False
    image_present: bool = False
    repeated_text: bool = False
    unique_speakers: int = 0
    latest_message_age: float = 0.0

    def as_dict(self) -> dict:
        data = {k: getattr(self, k) for k in ("direct_address", "reply_to_bot", "question", "funny", "serious", "continuity", "callback_candidate", "image_present", "repeated_text", "unique_speakers", "latest_message_age")}
        data["activity"] = {"state": self.activity.state, "messages_per_minute": self.activity.messages_per_minute, "quiet_minutes": round(self.activity.quiet_minutes, 1), "recent_bot_messages": self.activity.recent_bot_messages, "consecutive_bot_messages": self.activity.consecutive_bot_messages}
        return data

    def context_score(self) -> float:
        score = 0.0
        score += 0.28 if self.direct_address else 0.0
        score += 0.22 if self.reply_to_bot else 0.0
        score += 0.12 if self.question else 0.0
        score += 0.16 * self.funny
        score += 0.10 * self.continuity
        score += 0.08 if self.callback_candidate else 0.0
        score += 0.08 if self.image_present else 0.0
        score -= 0.28 * self.serious
        score -= 0.18 if self.repeated_text else 0.0
        return max(0.0, min(1.0, score))


def analyze(messages: list[ChatMessage], *, bot_username: str = "") -> SocialSignals:
    now = time.time()
    recent = [m for m in messages if now - m.timestamp <= 60]
    last = messages[-1] if messages else None
    age = max(0.0, now - last.timestamp) if last else 0.0
    bot_tail = 0
    for m in reversed(messages):
        if m.is_bot:
            bot_tail += 1
        else:
            break
    act = Activity(
        messages_per_minute=len(recent),
        state=activity_state(len(recent), age / 60 if last else 999),
        quiet_minutes=age / 60 if last else 999,
        recent_bot_messages=sum(m.is_bot for m in messages[-8:]),
        consecutive_bot_messages=bot_tail,
    )
    text = " ".join(m.text for m in messages[-12:] if m.text)
    latest_text = last.text if last else ""
    direct = False
    if bot_username and latest_text:
        low = latest_text.lower()
        name = bot_username.lower().lstrip("@")
        direct = (f"@{name}" in low) or bool(name and re.search(rf"(?<![\w@]){re.escape(name)}(?![\w])", low))
    reply_to_bot = bool(last and last.reply_to_message_id and any(x.message_id == last.reply_to_message_id and x.is_bot for x in messages))
    funny = min(1.0, len(LAUGHTER.findall(text)) / 5.0)
    serious = min(1.0, len(SERIOUS.findall(latest_text)) / 2.0)
    question = bool(QUESTION.search(latest_text))
    normalized = re.sub(r"\W+", " ", latest_text.lower()).strip()
    previous = [re.sub(r"\W+", " ", m.text.lower()).strip() for m in messages[-8:-1] if m.text]
    repeated = bool(normalized and normalized in previous)
    continuity = 0.0
    if last and len(messages) >= 2:
        if last.reply_to_message_id and any(x.message_id == last.reply_to_message_id for x in messages[-10:]):
            continuity += 0.55
        if len(last.text) >= 20:
            continuity += 0.20
        if len(set(m.user_id for m in messages[-10:])) >= 3:
            continuity += 0.15
    callback = bool(messages and any((now - m.timestamp) >= 300 and m.text for m in messages[:-1]))
    image_present = any(m.media_type == "photo" for m in messages[-6:])
    return SocialSignals(act, direct, reply_to_bot, question, funny, serious, min(1.0, continuity), callback, image_present, repeated, len(set(m.user_id for m in messages[-10:])), age)
