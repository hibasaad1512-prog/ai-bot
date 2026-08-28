from __future__ import annotations
from dataclasses import dataclass

@dataclass(slots=True)
class Activity:
    messages_per_minute: float
    state: str
    quiet_minutes: float
    recent_bot_messages: int
    consecutive_bot_messages: int

@dataclass(slots=True)
class ScoreInput:
    personality_chaos: int
    mentioned: bool
    reply_to_bot: bool
    funny_context: float
    useful_context: float
    continuity: float
    image_opportunity: float
    event_opportunity: float
    action_recently_used: bool
    cooldown_active: bool
    hourly_count: int
    hard_limit: int
    activity: Activity
    question: bool = False
    serious_context: float = 0.0
    repeated_context: bool = False
    direct_address_strength: float = 0.0


def activity_state(messages_per_minute: float, quiet_minutes: float) -> str:
    if quiet_minutes >= 10 and messages_per_minute < 1.0:
        return "QUIET"
    if messages_per_minute >= 80:
        return "VERY_ACTIVE"
    if messages_per_minute >= 25:
        return "ACTIVE"
    return "NORMAL"


def intervention_score(x: ScoreInput) -> float:
    score = 0.38 * x.personality_chaos
    score += 18 if x.mentioned else 0
    score += 14 if x.reply_to_bot else 0
    score += 10 if x.question else 0
    score += 16 * max(0, min(1, x.funny_context))
    score += 7 * max(0, min(1, x.useful_context))
    score += 12 * max(0, min(1, x.continuity))
    score += 8 * max(0, min(1, x.image_opportunity))
    score += 7 * max(0, min(1, x.event_opportunity))
    score += 10 * max(0, min(1, x.direct_address_strength))
    if x.activity.state == "QUIET": score += 5
    elif x.activity.state == "VERY_ACTIVE": score -= 25
    elif x.activity.state == "ACTIVE": score -= 11
    score -= min(27, x.activity.recent_bot_messages * 9)
    score -= min(22, x.activity.consecutive_bot_messages * 12)
    score -= 18 * max(0, min(1, x.serious_context))
    if x.repeated_context: score -= 12
    if x.action_recently_used: score -= 12
    if x.cooldown_active: score = 0
    if x.hourly_count >= x.hard_limit: score = 0
    elif x.hourly_count >= int(x.hard_limit * 0.8): score -= 15
    return max(0, min(100, score))
