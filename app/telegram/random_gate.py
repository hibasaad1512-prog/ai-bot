from __future__ import annotations

import random
import threading
import types

from app.config import settings
from app.telegram.permissions import is_group


class _GateState(threading.local):
    allow_ai = True
    chat_id = 0
    claimed = False


def install(handlers) -> None:
    """Install one concurrency-safe gate in front of normal AI generation."""
    if getattr(handlers, "_random_gate_installed", False):
        return

    ai = getattr(getattr(handlers, "rt", None), "ai", None)
    chaos = getattr(getattr(handlers, "rt", None), "chaos", None)
    cooldowns = getattr(chaos, "cooldowns", None)
    original_message = getattr(handlers, "on_message", None)
    original_generate = getattr(ai, "generate_text", None)
    if not callable(original_message) or not callable(original_generate) or cooldowns is None:
        return

    state = _GateState()

    def gated_generate(instance, prompt, system=None):
        if not getattr(state, "allow_ai", True):
            return ""
        try:
            result = original_generate(prompt, system)
            if not str(result or "").strip() and getattr(state, "claimed", False):
                cooldowns.release_global(getattr(state, "chat_id", 0))
                state.claimed = False
            return result
        except Exception:
            if getattr(state, "claimed", False):
                cooldowns.release_global(getattr(state, "chat_id", 0))
                state.claimed = False
            raise

    ai.generate_text = types.MethodType(gated_generate, ai)

    def wrapped(instance, message):
        state.allow_ai = True
        state.claimed = False
        state.chat_id = int(getattr(getattr(message, "chat", None), "id", 0) or 0)

        if (
            not is_group(getattr(getattr(message, "chat", None), "type", ""))
            or not getattr(message, "text", None)
            or getattr(getattr(message, "from_user", None), "is_bot", False)
        ):
            return original_message(message)

        # A human message breaks the consecutive-bot streak immediately.
        cooldowns.record_human_message(state.chat_id)

        text = str(message.text or "").strip()
        username = str(getattr(instance, "_bot_username", "") or "").lstrip("@").lower()
        mentioned = bool(username and username in text.lower())
        replied_to_bot = bool(
            getattr(message, "reply_to_message", None)
            and getattr(getattr(message.reply_to_message, "from_user", None), "is_bot", False)
        )
        question = "?" in text or text.endswith(("؟", "?"))

        chance = float(settings.reply_chance)
        if mentioned or replied_to_bot:
            chance = min(0.97, chance + 0.15)
        elif question:
            chance = min(0.92, chance + 0.07)

        # One random decision per message; no hidden second roll.
        if random.random() >= chance:
            state.allow_ai = False
            return original_message(message)

        # Reserve the global slot before the expensive AI request. The normal
        # handler commits hourly/consecutive counters only after it sends.
        if not cooldowns.try_gate(
            state.chat_id,
            global_cooldown=cooldowns.random_gap(
                settings.min_cooldown_seconds,
                settings.max_cooldown_seconds,
            ),
            hourly_limit=settings.hard_hourly_limit,
            max_consecutive=settings.max_consecutive_bot_messages,
        ):
            state.allow_ai = False
            return original_message(message)

        state.claimed = True
        try:
            return original_message(message)
        finally:
            # If the normal handler did not actually produce an AI reply,
            # don't leave a pre-AI reservation behind.
            if state.claimed:
                cooldowns.release_global(state.chat_id)
                state.claimed = False

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._random_gate_installed = True
