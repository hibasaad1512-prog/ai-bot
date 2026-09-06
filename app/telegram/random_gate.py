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
    """Install one concurrency-safe gate in front of normal AI generation.

    The existing message handler still records memory, moderation and media,
    but the AI call is suppressed when the probabilistic gate says no.
    """
    if getattr(handlers, "_random_gate_installed", False):
        return

    ai = getattr(getattr(handlers, "rt", None), "ai", None)
    cooldowns = getattr(getattr(handlers, "rt", None), "chaos", None)
    cooldowns = getattr(cooldowns, "cooldowns", None)
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

        text = str(message.text or "").strip()
        username = str(getattr(instance, "_bot_username", "") or "").lstrip("@").lower()
        mentioned = bool(username and username in text.lower())
        replied_to_bot = bool(
            getattr(message, "reply_to_message", None)
            and getattr(getattr(message.reply_to_message, "from_user", None), "is_bot", False)
        )
        question = "?" in text or text.endswith(("؟", "?"))

        # Explicitly addressed messages are highly likely, not guaranteed.
        chance = float(settings.reply_chance)
        if mentioned or replied_to_bot:
            chance = min(0.97, chance + 0.15)
        elif question:
            chance = min(0.92, chance + 0.07)

        # A single random decision is made for this message. This fixes the
        # old hard-coded 100% path while keeping direct conversation responsive.
        if random.random() >= chance:
            state.allow_ai = False
            return original_message(message)

        # Reserve the global anti-spam slot before the expensive AI request.
        # record_action() later commits the successful response to hourly and
        # consecutive counters. If AI fails, the reservation is released.
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
            result = original_message(message)
            return result
        finally:
            # A successful original handler records the action itself. If it
            # never called generate_text, don't leave the reservation hanging.
            if state.claimed:
                cooldowns.release_global(state.chat_id)
                state.claimed = False

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._random_gate_installed = True
