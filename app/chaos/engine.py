from __future__ import annotations

import random
from dataclasses import dataclass

from app.config import settings
from app.models import ChatMessage
from .actions import Action, DEFAULT_ACTIONS
from .cooldowns import CooldownStore
from .personality import Personality
from .scoring import ScoreInput, intervention_score
from .selector import choose_action
from .social import SocialSignals, analyze


@dataclass(slots=True)
class Decision:
    should_act: bool
    action: Action
    score: float
    confidence: float = 0.0
    signals: SocialSignals | None = None


class ChaosEngine:
    """Deterministic social scoring + probabilistic action selection.

    The engine only *selects* an action. The caller must run `claim_action`
    immediately before the actual Telegram side effect. This separation makes
    it impossible for decision generation itself to consume a cooldown slot.
    """

    def __init__(self):
        self.cooldowns = CooldownStore()

    def decide(
        self,
        chat_id: int,
        messages: list[ChatMessage],
        personality: Personality,
        mentioned: bool = False,
        reply_to_bot: bool = False,
        image_opportunity: float = 0,
        event_opportunity: float = 0,
        funny_context: float = 0.4,
        useful_context: float = 0.2,
        continuity: float = 0.4,
        bot_username: str = "",
    ) -> Decision:
        signals = analyze(messages, bot_username=bot_username)
        signals.direct_address = signals.direct_address or mentioned
        signals.reply_to_bot = signals.reply_to_bot or reply_to_bot
        signals.image_present = signals.image_present or image_opportunity > 0

        blocked = {
            action
            for action in DEFAULT_ACTIONS
            if self.cooldowns.action_active(chat_id, action.value)
        }
        score_input = ScoreInput(
            personality_chaos=personality.chaos,
            mentioned=signals.direct_address,
            reply_to_bot=signals.reply_to_bot,
            funny_context=max(funny_context, signals.funny),
            useful_context=useful_context,
            continuity=max(continuity, signals.continuity),
            image_opportunity=max(image_opportunity, 1.0 if signals.image_present else 0.0),
            event_opportunity=event_opportunity,
            action_recently_used=bool(blocked),
            cooldown_active=self.cooldowns.active(f"chat:{chat_id}"),
            hourly_count=self.cooldowns.hourly_count(chat_id),
            hard_limit=settings.hard_hourly_limit,
            activity=signals.activity,
            question=signals.question,
            serious_context=signals.serious,
            repeated_context=signals.repeated_text,
            direct_address_strength=1.0 if signals.direct_address else 0.0,
        )
        score = max(0.0, min(100.0, intervention_score(score_input)))

        if signals.direct_address or signals.reply_to_bot:
            score = max(score, min(78.0, 48.0 + personality.social * 0.25))

        if score <= 0 or self.cooldowns.active(f"chat:{chat_id}"):
            return Decision(False, Action.IGNORE, score, 0.0, signals)

        ai_gate = score >= settings.ai_min_score or signals.direct_address or signals.reply_to_bot or signals.question
        if not ai_gate:
            return Decision(False, Action.IGNORE, score, score / 100.0, signals)

        # The score controls the probability, while the action selector adds a
        # second layer of weighted randomness. Direct messages are favored but
        # are not guaranteed unless the final handler chooses to force them.
        if random.random() > score / 100.0:
            return Decision(False, Action.IGNORE, score, score / 100.0, signals)

        action = choose_action(score, blocked=blocked)
        return Decision(action != Action.IGNORE, action, score, min(1.0, score / 100.0), signals)

    def claim_action(self, chat_id: int, action: Action) -> bool:
        """Atomically reserve all anti-spam gates for a selected action."""
        if action == Action.IGNORE:
            return False
        spec = DEFAULT_ACTIONS.get(action)
        if spec is None:
            return False
        return self.cooldowns.claim(
            chat_id,
            action.value,
            action_cooldown=spec.cooldown,
            global_cooldown=self.cooldowns.random_gap(
                settings.min_cooldown_seconds,
                settings.max_cooldown_seconds,
            ),
            hourly_limit=settings.hard_hourly_limit,
            max_consecutive=settings.max_consecutive_bot_messages,
        )

    def mark_human_message(self, chat_id: int) -> None:
        self.cooldowns.record_human_message(chat_id)
