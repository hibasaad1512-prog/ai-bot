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

        if random.random() >= float(settings.proactive_chance):
            runtime.mark_proactive_done(chat_id)
            return

        try:
            # The legacy handler has its own in-memory timer. The persistent
            # runtime is now authoritative, so force that secondary timer due.
            next_map = getattr(instance, "_next_proactive", None)
            if isinstance(next_map, dict):
                next_map[chat_id] = 0
            original(chat_id)
        finally:
            # Always move the persistent window forward, including provider
            # failures, so an outage cannot create a retry storm.
            runtime.mark_proactive_done(chat_id)

    handlers.proactive = types.MethodType(wrapped, handlers)
    handlers._proactive_runtime_installed = True
