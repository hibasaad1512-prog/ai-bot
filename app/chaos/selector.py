from __future__ import annotations
import random
from .actions import Action, DEFAULT_ACTIONS


def choose_action(score: float, eligible: list[Action] | None = None, blocked: set[Action] | None = None) -> Action:
    allowed = eligible or list(DEFAULT_ACTIONS)
    blocked = blocked or set()
    choices=[]; weights=[]
    for action in allowed:
        if action in blocked:
            continue
        spec=DEFAULT_ACTIONS[action]
        if score >= spec.min_score:
            # Higher-value interventions become available only at higher scores.
            weight=spec.weight
            if action in {Action.GENERATE_IMAGE, Action.IMAGE_MASHUP, Action.CHAOS_EVENT, Action.FAKE_ANNOUNCEMENT}:
                weight *= max(0.1, (score-55)/45)
            choices.append(action); weights.append(weight)
    if not choices: return Action.IGNORE
    return random.choices(choices, weights=weights, k=1)[0]
