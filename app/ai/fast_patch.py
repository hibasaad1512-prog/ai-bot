from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)


def fast_call(self, prompt: str, system: str | None = None, response_format: dict[str, Any] | None = None):
    """Concurrent-safe Groq call: never hold the provider lock during HTTP."""
    last_error: Exception | None = None

    with self._lock:
        if not self.clients:
            raise RuntimeError("No Groq API keys configured")
        count = len(self.clients)
        start = self.current_key_index % count

    for offset in range(count):
        with self._lock:
            if not self.clients:
                break
            count_now = len(self.clients)
            index = (start + offset) % count_now
            key = self.keys[index]
            client = self.clients[index]
            model = self._key_models.get(key)

        if not model:
            try:
                self._refresh_key_health(index)
            except Exception:
                log.exception("fast Groq model refresh failed")
            with self._lock:
                if index >= len(self.keys):
                    continue
                key = self.keys[index]
                client = self.clients[index]
                model = self._key_models.get(key)

        if not model:
            with self._lock:
                self._last_failure[key] = time.time()
            continue

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._messages(prompt, system),
            "temperature": 0.8,
            "max_tokens": 300,
        }
        if model.startswith("openai/gpt-oss-"):
            kwargs["reasoning_effort"] = "low"
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            response = client.chat.completions.create(**kwargs)
            with self._lock:
                self.key_status[key] = {
                    **self.key_status.get(key, {}),
                    "status": "ready",
                    "last_error": None,
                    "last_used": time.time(),
                    "model": model,
                }
                if key in self.keys:
                    self.current_key_index = self.keys.index(key)
            return response
        except Exception as exc:
            last_error = exc
            now = time.time()
            with self._lock:
                self._last_failure[key] = now
                if self._is_rate_limited(exc):
                    status = "rate_limited"
                elif self._is_auth_error(exc):
                    status = "invalid"
                elif self._is_model_error(exc):
                    status = "model_unavailable"
                else:
                    status = "error"
                self.key_status[key] = {
                    **self.key_status.get(key, {}),
                    "status": status,
                    "last_error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "last_used": now,
                    "model": self._key_models.get(key),
                }
            log.warning("Fast Groq key #%d failed; trying next key", index + 1)
            continue

    raise RuntimeError("All Groq API keys failed") from last_error


def install() -> None:
    from app.ai.groq import GroqProvider
    GroqProvider._call = fast_call
