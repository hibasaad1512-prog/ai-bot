from __future__ import annotations

import random
import types

from app.config import settings


def install(handlers) -> None:
    """Make proactive timing persistent and apply one real chance gate."""
    if getattr(handlers, "_proactive_runtime_installed", False):
        return
    original = getattr(handlers, "proactive", None)
    runtime = getattr(handlers, "rt", None)
    if not callable(original) or runtime is None:
        return

    def wrapped(instance, chat_id: int):
        chat_id = int(chat_id)
        if not runtime.proactive_due(chat_id):
            return

        # Chance is evaluated only when the persistent timer is due.
        if random.random() >= float(settings.proactive_chance):
            runtime.mark_proactive_done(chat_id)
            return

        try:
            original(chat_id)
        finally:
            # Persist the next window even if the AI/provider failed. This
            # prevents a tight retry loop after an outage.
            runtime.mark_proactive_done(chat_id)

    handlers.proactive = types.MethodType(wrapped, handlers)
    handlers._proactive_runtime_installed = True
