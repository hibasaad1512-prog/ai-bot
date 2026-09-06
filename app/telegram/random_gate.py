from __future__ import annotations

import hashlib
import threading
import types

from app.config import settings
from app.telegram.permissions import is_group


class _GateState(threading.local):
    allow_ai = True
    chat_id = 0
    claimed = False


def _stable_random(chat_id: int, message_id: int, user_id: int, text: str) -> float:
    """Process-independent random value derived from Telegram message identity."""
    key = settings.telegram_bot_token.encode("utf-8")[:64]
    payload = f"{chat_id}:{message_id}:{user_id}:{text[:512]}".encode("utf-8", "ignore")
    digest = hashlib.blake2b(payload, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def _smart_chance(message, text: str) -> float:
    """Adjust probability from message semantics without server-side state."""
    chance = float(settings.reply_chance)
    lower = text.lower()
    username = str(getattr(message, "_bot_username", "") or "").lstrip("@").lower()
    if username and username in lower:
        chance += 0.16

    reply = getattr(message, "reply_to_message", None)
    if reply and getattr(getattr(reply, "from_user", None), "is_bot", False):
        chance += 0.16

    if "?" in text or "؟" in text:
        chance += 0.08

    if len(text) <= 2:
        chance -= 0.20
    elif len(text) <= 5:
        chance -= 0.08
    elif len(text) >= 180:
        chance += 0.03

    if any(word in lower for word in ("why", "how", "what", "who", "علاش", "كيف", "شنو", "واش", "فين")):
        chance += 0.05

    return max(0.0, min(0.97, chance))


def install(handlers) -> None:
    """Install a stateless, context-aware gate in front of normal AI replies."""
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

        cooldowns.record_human_message(state.chat_id)
        text = str(message.text or "").strip()
        user_id = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
        message_id = int(getattr(message, "message_id", 0) or 0)
        chance = _smart_chance(message, text)

        # No Python RNG state: restart/redeploy does not change this message's roll.
        if _stable_random(state.chat_id, message_id, user_id, text) >= chance:
            state.allow_ai = False
            return original_message(message)

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
            if state.claimed:
                cooldowns.release_global(state.chat_id)
                state.claimed = False

    handlers.on_message = types.MethodType(wrapped, handlers)
    handlers._random_gate_installed = True
