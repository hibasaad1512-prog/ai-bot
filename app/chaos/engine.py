from __future__ import annotations
import random, time
from dataclasses import dataclass
from app.models import ChatMessage
from .actions import Action, DEFAULT_ACTIONS
from .cooldowns import CooldownStore
from .personality import Personality
from .scoring import ScoreInput, intervention_score
from .selector import choose_action
from .social import analyze, SocialSignals
from app.config import settings

@dataclass(slots=True)
class Decision:
    should_act: bool
    action: Action
    score: float
    confidence: float = 0.0
    signals: SocialSignals | None = None

class ChaosEngine:
    def __init__(self): self.cooldowns = CooldownStore()

    def decide(self, chat_id: int, messages: list[ChatMessage], personality: Personality, mentioned: bool=False, reply_to_bot: bool=False, image_opportunity: float=0, event_opportunity: float=0, funny_context: float=0.4, useful_context: float=0.2, continuity: float=0.4, bot_username: str="") -> Decision:
        signals = analyze(messages, bot_username=bot_username)
        # Explicit handler signals override inference only when they are stronger.
        signals.direct_address = signals.direct_address or mentioned
        signals.reply_to_bot = signals.reply_to_bot or reply_to_bot
        signals.image_present = signals.image_present or image_opportunity > 0
        act = signals.activity
        blocked={a for a in DEFAULT_ACTIONS if self.cooldowns.action_active(chat_id,a.value)}
        inp=ScoreInput(
            personality_chaos=personality.chaos, mentioned=signals.direct_address, reply_to_bot=signals.reply_to_bot,
            funny_context=max(funny_context,signals.funny), useful_context=useful_context, continuity=max(continuity,signals.continuity),
            image_opportunity=max(image_opportunity,1.0 if signals.image_present else 0.0), event_opportunity=event_opportunity,
            action_recently_used=bool(blocked), cooldown_active=self.cooldowns.active(f"chat:{chat_id}"),
            hourly_count=self.cooldowns.hourly_count(chat_id), hard_limit=30, activity=act, question=signals.question,
            serious_context=signals.serious, repeated_context=signals.repeated_text, direct_address_strength=1.0 if signals.direct_address else 0.0,
        )
        score=intervention_score(inp)
        # Direct replies get a small deterministic floor; otherwise the score still controls silence.
        if signals.direct_address or signals.reply_to_bot:
            score=max(score, min(78.0, 48.0 + personality.social*0.25))
        if score <= 0 or self.cooldowns.active(f"chat:{chat_id}"):
            return Decision(False,Action.IGNORE,score,0.0,signals)
        # Do not wake the expensive AI for weak, low-signal messages.
        ai_gate = score >= settings.ai_min_score or signals.direct_address or signals.reply_to_bot or signals.question
        if not ai_gate or random.random() > score/100:
            return Decision(False,Action.IGNORE,score,score/100,signals)
        action=choose_action(score, blocked=blocked)
        return Decision(action != Action.IGNORE, action, score, min(1,score/100),signals)
