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

    Features:
    - Persistent multi-key storage in the bot database.
    - Automatic rotation: 1 -> 2 -> 3 -> ... -> 1.
    - Per-key model discovery.
    - Runtime add/delete/switch.
    - Key health tracking.
    - No API key is written to logs.
    - Compatible with generate_text().
    - Compatible with generate_structured().

    Keys are normally managed from Telegram using /123qrokz.

    Legacy environment variables are accepted only as bootstrap
    when the database has no saved keys.
    """

    STORAGE_CHAT_ID = 0

    STORAGE_DEFAULT = {
        "groq_keys": [],
        "current_index": 0,
    }

    FAILURE_COOLDOWN = 30.0

    MODEL_PREFERENCE = (
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    )

    def __init__(
        self,
        db=None,
    ):
        self.db = db

        self.clients: list[Any] = []
        self.keys: list[str] = []

        self.current_key_index: int = 0

        self.key_status: dict[
            str,
            dict[str, Any],
        ] = {}

        self._last_failure: dict[
            str,
            float,
        ] = {}

        self._key_models: dict[
            str,
            str,
        ] = {}

        self._lock = threading.RLock()

        # -----------------------------------------------------
        # Load saved database state.
        # -----------------------------------------------------

        saved = self._load_state()

        self.current_key_index = int(
            saved.get(
                "current_index",
                0,
            )
            or 0
        )

        for key in saved.get(
            "keys",
            [],
        ):
            self._add_client_internal(
                key,
                validate=False,
            )

        if self.clients:
            self.current_key_index %= len(
                self.clients
            )
        else:
            self.current_key_index = 0

        # -----------------------------------------------------
        # Legacy single-key ENV bootstrap.
        # -----------------------------------------------------

        if not self.clients:
            legacy = getattr(
                settings,
                "groq_api_key",
                "",
            ).strip()

            if legacy.startswith("gsk_"):
                if self._add_client_internal(
                    legacy,
                    validate=False,
                ):
                    self._save_state()

        # -----------------------------------------------------
        # Numbered ENV bootstrap.
        #
        # Example:
        # GROQ_API_KEY_1
        # GROQ_API_KEY_2
        # GROQ_API_KEY_3
        # -----------------------------------------------------

        if not self.clients:
            env_keys: list[
                tuple[int, str]
            ] = []

            for name, value in os.environ.items():

                if not name.startswith(
                    "GROQ_API_KEY_"
                ):
                    continue

                suffix = name.removeprefix(
                    "GROQ_API_KEY_"
                )

                if not suffix.isdigit():
                    continue

                value = value.strip()

                if value.startswith("gsk_"):
                    env_keys.append(
                        (
                            int(suffix),
                            value,
                        )
                    )

            env_keys.sort(
                key=lambda item: item[0]
            )

            for _, key in env_keys:
                self._add_client_internal(
                    key,
                    validate=False,
                )

            if self.clients:
                self.current_key_index = 0
                self._save_state()

        # -----------------------------------------------------
        # Health check all loaded keys.
        # -----------------------------------------------------

        self._refresh_all_key_health()

    # =========================================================
    # STATE / PERSISTENCE
    # =========================================================

    def _load_state(
        self,
    ) -> dict[str, Any]:

        if self.db is None:
            return {
                "keys": [],
                "current_index": 0,
            }

        try:
            data = self.db.get_json(
                "chat_settings",
                "chat_id",
                self.STORAGE_CHAT_ID,
                self.STORAGE_DEFAULT,
            )

            if not isinstance(
                data,
                dict,
            ):
                return {
                    "keys": [],
                    "current_index": 0,
                }

            raw = data.get(
                "groq_keys",
                data,
            )

            if isinstance(
                raw,
                dict,
            ):
                keys = raw.get(
                    "keys",
                    [],
                )

                current_index = raw.get(
                    "current_index",
                    0,
                )

            else:
                keys = raw
                current_index = 0

            if not isinstance(
                keys,
                list,
            ):
                keys = []

            clean: list[str] = []

            for key in keys:

                key = str(key).strip()

                if (
                    key.startswith("gsk_")
                    and key not in clean
                ):
                    clean.append(key)

            return {
                "keys": clean,
                "current_index": int(
                    current_index or 0
                ),
            }

        except Exception:
            log.exception(
                "Failed to load Groq key state"
            )

            return {
                "keys": [],
                "current_index": 0,
            }

    def _save_state(
        self,
    ) -> None:

        if self.db is None:
            return

        try:
            self.db.save_chat_settings(
                self.STORAGE_CHAT_ID,
                {
                    "groq_keys": {
                        "keys": list(
                            self.keys
                        ),
                        "current_index": int(
                            self.current_key_index
                        ),
                    }
                },
            )

        except Exception:
            log.exception(
                "Failed to save Groq key state"
            )

    # =========================================================
    # PROPERTIES
    # =========================================================

    @property
    def enabled(
        self,
    ) -> bool:

        with self._lock:
            return bool(
                self.clients
            )

    @property
    def current_key(
        self,
    ) -> str | None:

        with self._lock:

            if not self.keys:
                return None

            self.current_key_index %= len(
                self.keys
            )

            return self.keys[
                self.current_key_index
            ]

    @property
    def current_key_number(
        self,
    ) -> int | None:

        with self._lock:

            if not self.keys:
                return None

            self.current_key_index %= len(
                self.keys
            )

            return (
                self.current_key_index
                + 1
            )

    # =========================================================
    # KEY MASKING
    # =========================================================

    @staticmethod
    def mask_key(
        key: str,
    ) -> str:

        if not key:
            return "unknown"

        if len(key) <= 10:
            return "••••••••"

        return (
            f"{key[:6]}"
            "••••••••"
            f"{key[-4:]}"
        )

    # =========================================================
    # MODEL DISCOVERY
    # =========================================================

    def _list_model_ids(
        self,
        client: Any,
    ) -> list[str]:

        response = client.models.list()

        data = getattr(
            response,
            "data",
            None,
        )

        if data is None:
            return []

        result: list[str] = []

        for model in data:

            model_id = getattr(
                model,
                "id",
                None,
            )

            if model_id:
                result.append(
                    str(model_id)
                )

        return result

    def _choose_model(
        self,
        model_ids: list[str],
    ) -> str | None:

        available = set(
            model_ids
        )

        # First choice:
        # configured model if available.
        configured = getattr(
            settings,
            "groq_text_model",
            "",
        ).strip()

        if (
            configured
            and configured in available
        ):
            return configured

        # Preferred production models.
        for model_id in self.MODEL_PREFERENCE:

            if model_id in available:
                return model_id

        # Last text-model fallback.
        for model_id in model_ids:

            if "whisper" not in model_id.lower():
                return model_id

        return None

    def _validate_client(
        self,
        api_key: str,
        client: Any,
    ) -> tuple[
        bool,
        str | None,
        str | None,
    ]:
        """
        Check whether the key can access Groq models.

        Returns:
            (valid, selected_model, error)
        """

        try:

            model_ids = self._list_model_ids(
                client
            )

            selected_model = self._choose_model(
                model_ids
            )

            if selected_model is None:

                return (
                    False,
                    None,
                    "No compatible Groq text model is accessible",
                )

            return (
                True,
                selected_model,
                None,
            )

        except Exception as exc:

            return (
                False,
                None,
                (
                    f"{type(exc).__name__}: "
                    f"{str(exc)[:200]}"
                ),
            )

    # =========================================================
    # CLIENT CREATION
    # =========================================================

    def _add_client_internal(
        self,
        api_key: str,
        *,
        validate: bool = False,
    ) -> bool:

        api_key = api_key.strip()

        if not api_key.startswith(
            "gsk_"
        ):
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

                self.keys.append(
                    api_key
                )

                self.clients.append(
                    client
                )

                self.key_status[
                    api_key
                ] = {
                    "status": "ready",
                    "last_error": None,
                    "last_used": None,
                    "added_at": time.time(),
                }

                if validate:

                    ok, model, error = (
                        self._validate_client(
                            api_key,
                            client,
                        )
                    )

                    if ok and model:

                        self._key_models[
                            api_key
                        ] = model

                        self.key_status[
                            api_key
                        ] = {
                            **self.key_status[
                                api_key
                            ],
                            "status": "ready",
                            "model": model,
                            "last_checked": time.time(),
                        }

                    else:

                        self.key_status[
                            api_key
                        ] = {
                            **self.key_status[
                                api_key
                            ],
                            "status": "error",
                            "last_error": error,
                            "last_checked": time.time(),
                        }

                return True

            except Exception:

                log.exception(
                    "Groq client initialization failed"
                )

                return False

    # =========================================================
    # HEALTH CHECK
    # =========================================================

    def _refresh_key_health(
        self,
        index: int,
    ) -> bool:

        with self._lock:

            if (
                index < 0
                or index >= len(
                    self.clients
                )
            ):
                return False

            key = self.keys[index]
            client = self.clients[index]

        ok, model, error = (
            self._validate_client(
                key,
                client,
            )
        )

        with self._lock:

            if ok and model:

                self._key_models[
                    key
                ] = model

                self.key_status[
                    key
                ] = {
                    **self.key_status.get(
                        key,
                        {},
                    ),
                    "status": "ready",
                    "last_error": None,
                    "model": model,
                    "last_checked": time.time(),
                }

                return True

            error_lower = (
                (error or "")
                .lower()
            )

            is_auth = (
                "401" in error_lower
                or "403" in error_lower
                or "invalid api key"
                in error_lower
                or "authentication"
                in error_lower
            )

            self.key_status[
                key
            ] = {
                **self.key_status.get(
                    key,
                    {},
                ),
                "status": (
                    "invalid"
                    if is_auth
                    else "error"
                ),
                "last_error": error,
                "last_checked": time.time(),
            }

            return False

    def _refresh_all_key_health(
        self,
    ) -> None:

        for index in range(
            len(self.clients)
        ):
            self._refresh_key_health(
                index
            )

    # =========================================================
    # ADD KEY
    # =========================================================

    def add_key(
        self,
        api_key: str,
    ) -> tuple[
        bool,
        str,
    ]:

        api_key = api_key.strip()

        if not api_key.startswith(
            "gsk_"
        ):
            return (
                False,
                "invalid_format",
            )

        with self._lock:

            if api_key in self.keys:
                return (
                    False,
                    "already_exists",
                )

            try:

                from groq import Groq

                client = Groq(
                    api_key=api_key,
                    timeout=30.0,
                    max_retries=0,
                )

                ok, model, error = (
                    self._validate_client(
                        api_key,
                        client,
                    )
                )

                if not ok:

                    return (
                        False,
                        (
                            "validation_failed: "
                            + (
                                error
                                or "unknown error"
                            )
                        ),
                    )

                self.keys.append(
                    api_key
                )

                self.clients.append(
                    client
                )

                self._key_models[
                    api_key
                ] = model

                self.key_status[
                    api_key
                ] = {
                    "status": "ready",
                    "last_error": None,
                    "last_used": None,
                    "added_at": time.time(),
                    "last_checked": time.time(),
                    "model": model,
                }

                self._save_state()

                return (
                    True,
                    "added",
                )

            except Exception as exc:

                return (
                    False,
                    (
                        "validation_failed: "
                        f"{type(exc).__name__}: "
                        f"{str(exc)[:200]}"
                    ),
                )

    # =========================================================
    # DELETE KEY
    # =========================================================

    def delete_key(
        self,
        index: int,
    ) -> tuple[
        bool,
        str,
    ]:

        with self._lock:

            if (
                index < 0
                or index >= len(
                    self.keys
                )
            ):
                return (
                    False,
                    "invalid_index",
                )

            deleted_key = self.keys[
                index
            ]

            del self.keys[
                index
            ]

            del self.clients[
                index
            ]

            self.key_status.pop(
                deleted_key,
                None,
            )

            self._last_failure.pop(
                deleted_key,
                None,
            )

            self._key_models.pop(
                deleted_key,
                None,
            )

            if not self.keys:

                self.current_key_index = 0

            elif (
                self.current_key_index
                > index
            ):

                self.current_key_index -= 1

            elif (
                self.current_key_index
                >= len(self.keys)
            ):

                self.current_key_index = 0

            self._save_state()

            return (
                True,
                "deleted",
            )

    # =========================================================
    # SWITCH KEY
    # =========================================================

    def switch_key(
        self,
        index: int,
    ) -> bool:

        with self._lock:

            if (
                index < 0
                or index >= len(
                    self.keys
                )
            ):
                return False

            self.current_key_index = (
                index
            )

            self._save_state()

            return True

    # =========================================================
    # STATUS
    # =========================================================

    def get_key_status(
        self,
    ) -> list[
        dict[str, Any]
    ]:

        with self._lock:

            result: list[
                dict[str, Any]
            ] = []

            now = time.time()

            for index, key in enumerate(
                self.keys
            ):

                status = dict(
                    self.key_status.get(
                        key,
                        {},
                    )
                )

                failed_at = (
                    self._last_failure.get(
                        key
                    )
                )

                if (
                    status.get(
                        "status"
                    )
                    == "rate_limited"
                    and failed_at is not None
                    and (
                        now
                        - failed_at
                        >= self.FAILURE_COOLDOWN
                    )
                ):
                    status[
                        "status"
                    ] = "ready"

                result.append(
                    {
                        "index": index,
                        "key": key,
                        "masked": self.mask_key(
                            key
                        ),
                        "status": status.get(
                            "status",
                            "unknown",
                        ),
                        "last_error": status.get(
                            "last_error"
                        ),
                        "last_used": status.get(
                            "last_used"
                        ),
                        "last_checked": status.get(
                            "last_checked"
                        ),
                        "added_at": status.get(
                            "added_at"
                        ),
                        "model": self._key_models.get(
                            key
                        ),
                        "active": (
                            index
                            == self.current_key_index
                        ),
                    }
                )

            return result

    # =========================================================
    # ERROR HELPERS
    # =========================================================

    @staticmethod
    def _is_rate_limited(
        exc: Exception,
    ) -> bool:

        text = str(exc).lower()
        name = type(exc).__name__.lower()

        return (
            "429" in text
            or "rate limit" in text
            or "ratelimit" in text
            or "too many requests"
            in text
            or "quota" in text
            or "limit reached"
            in text
            or "rate_limit" in name
            or "ratelimit" in name
        )

    @staticmethod
    def _is_auth_error(
        exc: Exception,
    ) -> bool:

        text = str(exc).lower()

        return (
            "401" in text
            or "403" in text
            or "invalid api key"
            in text
            or "invalid authentication"
            in text
            or (
                "authentication"
                in text
                and "failed"
                in text
            )
        )

    @staticmethod
    def _is_model_error(
        exc: Exception,
    ) -> bool:

        text = str(exc).lower()

        return (
            "model" in text
            and (
                "404" in text
                or "does not exist"
                in text
                or "do not have access"
                in text
                or "not found"
                in text
            )
        )

    # =========================================================
    # ROTATION
    # =========================================================

    def _rotate_key(
        self,
    ) -> bool:

        with self._lock:

            if not self.clients:
                return False

            if len(self.clients) == 1:
                return True

            start = (
                self.current_key_index
            )

            now = time.time()

            for offset in range(
                1,
                len(self.clients) + 1,
            ):

                index = (
                    start
                    + offset
                ) % len(
                    self.clients
                )

                key = self.keys[
                    index
                ]

                failed_at = (
                    self._last_failure.get(
                        key,
                        0.0,
                    )
                )

                if (
                    now - failed_at
                    < self.FAILURE_COOLDOWN
                ):
                    continue

                self.current_key_index = (
                    index
                )

                self._save_state()

                return True

            # All keys are cooling down.
            # Keep the cycle circular.
            self.current_key_index = (
                start + 1
            ) % len(
                self.clients
            )

            self._save_state()

            return True

    # =========================================================
    # API CALL
    # =========================================================

    def _call(
        self,
        prompt: str,
        system: str | None = None,
        response_format: dict[
            str,
            Any,
        ]
        | None = None,
    ):

        with self._lock:

            if not self.clients:
                raise RuntimeError(
                    "No Groq API keys configured"
                )

            attempts = len(
                self.clients
            )

            last_error: Exception | None = (
                None
            )

            for _ in range(
                attempts
            ):

                if not self.clients:
                    break

                index = (
                    self.current_key_index
                    % len(
                        self.clients
                    )
                )

                key = self.keys[
                    index
                ]

                client = self.clients[
                    index
                ]

                model = self._key_models.get(
                    key
                )

                # -------------------------------------------------
                # If model isn't known, discover it.
                # -------------------------------------------------

                if not model:

                    self._refresh_key_health(
                        index
                    )

                    model = (
                        self._key_models.get(
                            key
                        )
                    )

                if not model:

                    self._last_failure[
                        key
                    ] = time.time()

                    self._rotate_key()

                    continue

                kwargs: dict[
                    str,
                    Any,
                ] = {
                    "model": model,
                    "messages": self._messages(
                        prompt,
                        system,
                    ),
                    "temperature": 0.8,
                    "max_tokens": 400,
                }

                if model.startswith(
                    "openai/gpt-oss-"
                ):

                    kwargs[
                        "reasoning_effort"
                    ] = "low"

                if response_format is not None:

                    kwargs[
                        "response_format"
                    ] = response_format

                try:

                    response = (
                        client
                        .chat
                        .completions
                        .create(
                            **kwargs
                        )
                    )

                    self.key_status[
                        key
                    ] = {
                        **self.key_status.get(
                            key,
                            {},
                        ),
                        "status": "ready",
                        "last_error": None,
                        "last_used": time.time(),
                        "model": model,
                    }

                    return response

                except Exception as exc:

                    last_error = exc

                    now = time.time()

                    self._last_failure[
                        key
                    ] = now

                    # -------------------------------------------------
                    # Model problem:
                    # refresh this key before rotating it away.
                    # -------------------------------------------------

                    if self._is_model_error(
                        exc
                    ):

                        refreshed = (
                            self._refresh_key_health(
                                index
                            )
                        )

                        if refreshed:

                            refreshed_model = (
                                self._key_models.get(
                                    key
                                )
                            )

                            if (
                                refreshed_model
                                and refreshed_model
                                != model
                            ):

                                continue

                    if self._is_rate_limited(
                        exc
                    ):

                        status = (
                            "rate_limited"
                        )

                    elif self._is_auth_error(
                        exc
                    ):

                        status = "invalid"

                    elif self._is_model_error(
                        exc
                    ):

                        status = (
                            "model_unavailable"
                        )

                    else:

                        status = "error"

                    self.key_status[
                        key
                    ] = {
                        **self.key_status.get(
                            key,
                            {},
                        ),
                        "status": status,
                        "last_error": (
                            f"{type(exc).__name__}: "
                            f"{str(exc)[:200]}"
                        ),
                        "last_used": now,
                        "model": self._key_models.get(
                            key
                        ),
                    }

                    log.warning(
                        "Groq key #%d failed; rotating",
                        index + 1,
                    )

                    self._rotate_key()

            raise RuntimeError(
                "All Groq API keys failed"
            ) from last_error

    # =========================================================
    # MESSAGES
    # =========================================================

    @staticmethod
    def _messages(
        prompt: str,
        system: str | None = None,
    ) -> list[
        dict[str, str]
    ]:

        messages: list[
            dict[str, str]
        ] = []

        if system:

            messages.append(
                {
                    "role": "system",
                    "content": system,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        return messages

    # =========================================================
    # TEXT
    # =========================================================

    def generate_text(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:

        response = self._call(
            prompt,
            system,
        )

        content = (
            response
            .choices[0]
            .message
            .content
            or ""
        )

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

        structured_schema = dict(
            DECISION_SCHEMA
        )

        structured_schema[
            "additionalProperties"
        ] = False

        response = self._call(
            prompt,
            system,
            {
                "type": "json_schema",
                "json_schema": {
                    "name": (
                        "Lmyrfawya_decision"
                    ),
                    "strict": True,
                    "schema": (
                        structured_schema
                    ),
                },
            },
        )

        raw = (
            response
            .choices[0]
            .message
            .content
            or "{}"
        )

        try:
            return json.loads(
                raw
            )

        except json.JSONDecodeError:

            log.exception(
                "Invalid structured response from Groq"
            )

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
            "Groq provider does not expose image vision "
            "in this bot build"
        )

    # =========================================================
    # IMAGE GENERATION
    # =========================================================

    def generate_image(
        self,
        prompt: str,
    ) -> bytes | None:

        return None