from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from .base import AIProvider
from .schemas import DECISION_SCHEMA
from app.config import settings

log = logging.getLogger(__name__)


class GroqProvider(AIProvider):
    """
    Groq provider with persistent multi-key rotation.

    Keys are stored in the bot database under chat_settings/chat_id=0.
    No Groq key is required in .env for normal operation.

    Key management is exposed through handlers.py (/123qrokz).
    """

    STORAGE_CHAT_ID = 0
    STORAGE_DEFAULT = {"groq_keys": []}
    FAILURE_COOLDOWN = 30.0

    def __init__(self, db=None):
        self.db = db
        self.clients: list[Any] = []
        self.keys: list[str] = []
        self.current_key_index: int = 0
        self.key_status: dict[str, dict[str, Any]] = {}
        self._last_failure: dict[str, float] = {}
        self._lock = threading.RLock()

        saved = self._load_state()
        self.current_key_index = int(saved.get("current_index", 0) or 0)

        for key in saved.get("keys", []):
            self._add_client_internal(key)

        if self.clients:
            self.current_key_index %= len(self.clients)
        else:
            self.current_key_index = 0

        # Optional backwards compatibility only. If the old single-key
        # environment variable exists and the DB is empty, import it once.
        if not self.clients:
            legacy = getattr(settings, "groq_api_key", "").strip()
            if legacy.startswith("gsk_"):
                if self._add_client_internal(legacy):
                    self._save_state()

        # Also accept numbered env keys only as a one-time bootstrap.
        if not self.clients:
            env_keys = []
            for name, value in os.environ.items():
                if not name.startswith("GROQ_API_KEY_"):
                    continue
                suffix = name.removeprefix("GROQ_API_KEY_")
                if not suffix.isdigit():
                    continue
                value = value.strip()
                if value.startswith("gsk_"):
                    env_keys.append((int(suffix), value))

            env_keys.sort(key=lambda item: item[0])
            for _, key in env_keys:
                self._add_client_internal(key)

            if self.clients:
                self.current_key_index = 0
                self._save_state()

    # =========================================================
    # STATE / PERSISTENCE
    # =========================================================

    def _load_state(self) -> dict[str, Any]:
        if self.db is None:
            return {"keys": [], "current_index": 0}

        try:
            data = self.db.get_json(
                "chat_settings",
                "chat_id",
                self.STORAGE_CHAT_ID,
                self.STORAGE_DEFAULT,
            )

            if not isinstance(data, dict):
                return {"keys": [], "current_index": 0}

            raw = data.get("groq_keys", data)

            if isinstance(raw, dict):
                keys = raw.get("keys", [])
                current_index = raw.get("current_index", 0)
            else:
                keys = raw
                current_index = 0

            if not isinstance(keys, list):
                keys = []

            clean: list[str] = []
            for key in keys:
                key = str(key).strip()
                if key.startswith("gsk_") and key not in clean:
                    clean.append(key)

            return {
                "keys": clean,
                "current_index": int(current_index or 0),
            }

        except Exception:
            log.exception("Failed to load Groq key state")
            return {"keys": [], "current_index": 0}

    def _save_state(self) -> None:
        if self.db is None:
            return

        try:
            self.db.save_chat_settings(
                self.STORAGE_CHAT_ID,
                {
                    "groq_keys": {
                        "keys": list(self.keys),
                        "current_index": int(self.current_key_index),
                    }
                },
            )
        except Exception:
            log.exception("Failed to save Groq key state")

    # =========================================================
    # PROPERTIES
    # =========================================================

    @property
    def enabled(self) -> bool:
        with self._lock:
            return bool(self.clients)

    @property
    def current_key(self) -> str | None:
        with self._lock:
            if not self.keys:
                return None
            self.current_key_index %= len(self.keys)
            return self.keys[self.current_key_index]

    @property
    def current_key_number(self) -> int | None:
        with self._lock:
            if not self.keys:
                return None
            self.current_key_index %= len(self.keys)
            return self.current_key_index + 1

    # =========================================================
    # MASKING
    # =========================================================

    @staticmethod
    def mask_key(key: str) -> str:
        if not key:
            return "unknown"
        if len(key) <= 10:
            return "••••••••"
        return f"{key[:6]}••••••••{key[-4:]}"

    # =========================================================
    # INTERNAL CLIENT CREATION
    # =========================================================

    def _add_client_internal(self, api_key: str) -> bool:
        api_key = api_key.strip()

        if not api_key.startswith("gsk_"):
            return False

        with self._lock:
            if api_key in self.keys:
                return False

            try:
                from groq import Groq

                client = Groq(
                    api_key=api_key,
                    timeout=30.0,
                    max_retries=0,
                )

                self.keys.append(api_key)
                self.clients.append(client)
                self.key_status[api_key] = {
                    "status": "ready",
                    "last_error": None,
                    "last_used": None,
                    "added_at": time.time(),
                }
                return True

            except Exception:
                log.exception("Groq client initialization failed")
                return False

    # =========================================================
    # PUBLIC KEY MANAGEMENT
    # =========================================================

    def add_key(self, api_key: str) -> tuple[bool, str]:
        api_key = api_key.strip()

        if not api_key.startswith("gsk_"):
            return False, "invalid_format"

        with self._lock:
            if api_key in self.keys:
                return False, "already_exists"

            if not self._add_client_internal(api_key):
                return False, "initialization_failed"

            self._save_state()
            return True, "added"

    def delete_key(self, index: int) -> tuple[bool, str]:
        with self._lock:
            if index < 0 or index >= len(self.keys):
                return False, "invalid_index"

            deleted_key = self.keys[index]

            del self.keys[index]
            del self.clients[index]
            self.key_status.pop(deleted_key, None)
            self._last_failure.pop(deleted_key, None)

            if not self.keys:
                self.current_key_index = 0
            elif self.current_key_index > index:
                self.current_key_index -= 1
            elif self.current_key_index >= len(self.keys):
                self.current_key_index = 0

            self._save_state()
            return True, "deleted"

    def switch_key(self, index: int) -> bool:
        with self._lock:
            if index < 0 or index >= len(self.keys):
                return False

            self.current_key_index = index
            self._save_state()
            return True

    # =========================================================
    # STATUS
    # =========================================================

    def get_key_status(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []

            for index, key in enumerate(self.keys):
                status = dict(
                    self.key_status.get(key, {})
                )

                failed_at = self._last_failure.get(key)
                if (
                    status.get("status") == "rate_limited"
                    and failed_at is not None
                    and time.time() - failed_at >= self.FAILURE_COOLDOWN
                ):
                    status["status"] = "ready"

                result.append(
                    {
                        "index": index,
                        "key": key,
                        "masked": self.mask_key(key),
                        "status": status.get("status", "unknown"),
                        "last_error": status.get("last_error"),
                        "last_used": status.get("last_used"),
                        "added_at": status.get("added_at"),
                        "active": index == self.current_key_index,
                    }
                )

            return result

    # =========================================================
    # ROTATION
    # =========================================================

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        text = str(exc).lower()
        name = type(exc).__name__.lower()
        return (
            "429" in text
            or "rate limit" in text
            or "ratelimit" in text
            or "too many requests" in text
            or "quota" in text
            or "limit reached" in text
            or "rate_limit" in name
            or "ratelimit" in name
        )

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "401" in text
            or "403" in text
            or "invalid api key" in text
            or "invalid authentication" in text
            or "authentication" in text and "failed" in text
        )

    def _rotate_key(self) -> bool:
        with self._lock:
            if not self.clients:
                return False

            if len(self.clients) == 1:
                return True

            start = self.current_key_index
            now = time.time()

            for offset in range(1, len(self.clients) + 1):
                index = (start + offset) % len(self.clients)
                key = self.keys[index]
                failed_at = self._last_failure.get(key, 0.0)

                if now - failed_at < self.FAILURE_COOLDOWN:
                    continue

                self.current_key_index = index
                self._save_state()
                return True

            # All keys are cooling down. Still move forward so the
            # cycle remains circular: 1 -> 2 -> 3 -> 4 -> 1.
            self.current_key_index = (start + 1) % len(self.clients)
            self._save_state()
            return True

    # =========================================================
    # API CALL
    # =========================================================

    def _call(
        self,
        prompt: str,
        system: str | None = None,
        response_format: dict[str, Any] | None = None,
    ):
        with self._lock:
            if not self.clients:
                raise RuntimeError("No Groq API keys configured")

            attempts = len(self.clients)
            last_error: Exception | None = None

            for _ in range(attempts):
                index = self.current_key_index % len(self.clients)
                key = self.keys[index]
                client = self.clients[index]

                kwargs: dict[str, Any] = {
                    "model": settings.groq_text_model,
                    "messages": self._messages(prompt, system),
                    "temperature": 0.8,
                    "max_tokens": 400,
                }

                if settings.groq_text_model.startswith("openai/gpt-oss-"):
                    kwargs["reasoning_effort"] = "low"

                if response_format is not None:
                    kwargs["response_format"] = response_format

                try:
                    response = client.chat.completions.create(**kwargs)

                    self.key_status[key] = {
                        **self.key_status.get(key, {}),
                        "status": "ready",
                        "last_error": None,
                        "last_used": time.time(),
                    }

                    return response

                except Exception as exc:
                    last_error = exc
                    now = time.time()
                    self._last_failure[key] = now

                    if self._is_rate_limited(exc):
                        status = "rate_limited"
                    elif self._is_auth_error(exc):
                        status = "invalid"
                    else:
                        status = "error"

                    self.key_status[key] = {
                        **self.key_status.get(key, {}),
                        "status": status,
                        "last_error": f"{type(exc).__name__}: {str(exc)[:200]}",
                        "last_used": now,
                    }

                    log.warning(
                        "Groq key #%d failed; rotating",
                        index + 1,
                    )
                    self._rotate_key()

            raise RuntimeError("All Groq API keys failed") from last_error

    # =========================================================
    # MESSAGES
    # =========================================================

    @staticmethod
    def _messages(
        prompt: str,
        system: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        if system:
            messages.append({
                "role": "system",
                "content": system,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        return messages

    # =========================================================
    # TEXT
    # =========================================================

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        response = self._call(prompt, system)
        content = response.choices[0].message.content or ""
        return content.strip()

    # =========================================================
    # STRUCTURED
    # =========================================================

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        system: str | None = None,
    ) -> dict[str, Any]:
        structured_schema = dict(DECISION_SCHEMA)
        structured_schema["additionalProperties"] = False

        response = self._call(
            prompt,
            system,
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "Lmyrfawya_decision",
                    "strict": True,
                    "schema": structured_schema,
                },
            },
        )

        raw = response.choices[0].message.content or "{}"

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.exception("Invalid structured response from Groq")
            return {}

    # =========================================================
    # VISION
    # =========================================================

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
    ) -> str:
        raise RuntimeError(
            "Groq provider does not expose image vision in this bot build"
        )

    # =========================================================
    # IMAGE GENERATION
    # =========================================================

    def generate_image(
        self,
        prompt: str,
    ) -> bytes | None:
        return None
