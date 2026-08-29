from __future__ import annotations

import logging
import random
import re
import threading
import time
from functools import wraps
from typing import Any, Callable, TypeVar


# =========================================================
# TELEGRAM RATE LIMIT / RETRY PROTECTION
# =========================================================
#
# Prevents Telegram API 429 errors from crashing the bot.
#
# Features:
#   - Global request spacing
#   - Automatic retry
#   - Reads Telegram retry_after when available
#   - Exponential backoff
#   - Jitter to prevent synchronized requests
#   - Thread-safe
#   - Never retries forever
#   - Compatible with synchronous pyTelegramBotAPI / telebot
#
# Usage:
#
#   from app.telegram.rate_limit import safe_telegram_call
#
#   safe_telegram_call(
#       bot.send_message,
#       chat_id,
#       "Hello"
#   )
#
# =========================================================


logger = logging.getLogger("karamel.telegram.rate_limit")


# =========================================================
# CONFIGURATION
# =========================================================

# Minimum time between Telegram API requests.
#
# Telegram has different limits for different methods/chats.
# A small global spacing greatly reduces accidental bursts.
MIN_REQUEST_INTERVAL = 0.12

# Maximum automatic retries after a 429.
MAX_RETRIES = 5

# Default wait when Telegram does not expose retry_after.
DEFAULT_RETRY_SECONDS = 1.0

# Maximum backoff delay.
MAX_BACKOFF_SECONDS = 15.0

# Small random delay added to retries.
JITTER_SECONDS = 0.15


# =========================================================
# GLOBAL STATE
# =========================================================

_request_lock = threading.Lock()

_last_request_time = 0.0


# =========================================================
# TYPE
# =========================================================

T = TypeVar("T")


# =========================================================
# RETRY_AFTER EXTRACTION
# =========================================================

def _extract_retry_after(exc: BaseException) -> float | None:
    """
    Try to extract Telegram's retry_after value from
    pyTelegramBotAPI exceptions.

    Telegram commonly returns:

        {
            "parameters": {
                "retry_after": 1
            }
        }

    Different pyTelegramBotAPI versions expose this
    information slightly differently, so we check several
    safe locations.
    """

    # -----------------------------------------------------
    # Direct attribute
    # -----------------------------------------------------

    value = getattr(exc, "retry_after", None)

    if value is not None:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            pass

    # -----------------------------------------------------
    # result_json
    # -----------------------------------------------------

    result_json = getattr(exc, "result_json", None)

    if isinstance(result_json, dict):

        parameters = result_json.get("parameters")

        if isinstance(parameters, dict):

            value = parameters.get("retry_after")

            if value is not None:
                try:
                    return max(0.0, float(value))
                except (TypeError, ValueError):
                    pass

    # -----------------------------------------------------
    # result object
    # -----------------------------------------------------

    result = getattr(exc, "result", None)

    if result is not None:

        parameters = getattr(
            result,
            "parameters",
            None,
        )

        if parameters is not None:

            value = getattr(
                parameters,
                "retry_after",
                None,
            )

            if value is not None:

                try:
                    return max(
                        0.0,
                        float(value),
                    )
                except (TypeError, ValueError):
                    pass

    # -----------------------------------------------------
    # Text fallback
    # -----------------------------------------------------

    text = str(exc)

    match = re.search(
        r"retry after\s+(\d+(?:\.\d+)?)",
        text,
        re.I,
    )

    if match:

        try:
            return max(
                0.0,
                float(match.group(1)),
            )
        except (TypeError, ValueError):
            pass

    return None


# =========================================================
# DETECT 429
# =========================================================

def is_rate_limit_error(
    exc: BaseException,
) -> bool:
    """
    Return True when an exception represents a Telegram
    429 Too Many Requests response.
    """

    status_code = getattr(
        exc,
        "error_code",
        None,
    )

    if status_code == 429:
        return True

    status_code = getattr(
        exc,
        "status_code",
        None,
    )

    if status_code == 429:
        return True

    text = str(exc).lower()

    return (
        "429" in text
        and (
            "too many requests" in text
            or "retry after" in text
        )
    )


# =========================================================
# REQUEST SPACING
# =========================================================

def _wait_for_request_slot() -> None:
    """
    Ensure Telegram requests are not fired in a burst.
    """

    global _last_request_time

    with _request_lock:

        now = time.monotonic()

        elapsed = (
            now - _last_request_time
        )

        if elapsed < MIN_REQUEST_INTERVAL:

            wait_time = (
                MIN_REQUEST_INTERVAL
                - elapsed
            )

            time.sleep(wait_time)

        _last_request_time = (
            time.monotonic()
        )


# =========================================================
# BACKOFF
# =========================================================

def _backoff_delay(
    attempt: int,
) -> float:
    """
    Exponential backoff with a small random jitter.
    """

    delay = min(
        DEFAULT_RETRY_SECONDS
        * (2 ** attempt),
        MAX_BACKOFF_SECONDS,
    )

    delay += random.uniform(
        0.0,
        JITTER_SECONDS,
    )

    return delay


# =========================================================
# SAFE TELEGRAM CALL
# =========================================================

def safe_telegram_call(
    function: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Execute a Telegram API call safely.

    Automatically handles 429 errors.

    Example:

        safe_telegram_call(
            bot.send_message,
            chat_id,
            "Hello"
        )
    """

    last_exception: BaseException | None = None

    for attempt in range(
        MAX_RETRIES + 1
    ):

        _wait_for_request_slot()

        try:

            return function(
                *args,
                **kwargs,
            )

        except Exception as exc:

            last_exception = exc

            # -------------------------------------------------
            # Non-429 errors are not hidden.
            # -------------------------------------------------

            if not is_rate_limit_error(exc):

                raise

            # -------------------------------------------------
            # Maximum retry count reached.
            # -------------------------------------------------

            if attempt >= MAX_RETRIES:

                logger.error(
                    "Telegram rate limit persisted "
                    "after %s retries.",
                    MAX_RETRIES,
                )

                raise

            # -------------------------------------------------
            # Telegram-provided retry_after.
            # -------------------------------------------------

            retry_after = (
                _extract_retry_after(exc)
            )

            if retry_after is None:

                retry_after = (
                    _backoff_delay(attempt)
                )

            else:

                # Add a tiny safety margin.
                retry_after += (
                    0.10
                )

                retry_after += random.uniform(
                    0.0,
                    JITTER_SECONDS,
                )

            retry_after = min(
                retry_after,
                MAX_BACKOFF_SECONDS,
            )

            logger.warning(
                "Telegram returned 429. "
                "Retrying in %.2f seconds "
                "(attempt %s/%s).",
                retry_after,
                attempt + 1,
                MAX_RETRIES,
            )

            time.sleep(
                retry_after
            )

    # This should never normally be reached.
    if last_exception is not None:
        raise last_exception

    raise RuntimeError(
        "Telegram request failed unexpectedly."
    )


# =========================================================
# DECORATOR
# =========================================================

def telegram_safe(
    function: Callable[..., T],
) -> Callable[..., T]:
    """
    Decorator version of safe_telegram_call.

    Example:

        @telegram_safe
        def send_message(...):
            return bot.send_message(...)
    """

    @wraps(function)
    def wrapper(
        *args: Any,
        **kwargs: Any,
    ) -> T:

        return safe_telegram_call(
            function,
            *args,
            **kwargs,
        )

    return wrapper


# =========================================================
# SAFE COMMON METHODS
# =========================================================

def safe_send_message(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.send_message().
    """

    return safe_telegram_call(
        bot.send_message,
        *args,
        **kwargs,
    )


def safe_reply_to(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.reply_to().
    """

    return safe_telegram_call(
        bot.reply_to,
        *args,
        **kwargs,
    )


def safe_edit_message_text(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.edit_message_text().
    """

    return safe_telegram_call(
        bot.edit_message_text,
        *args,
        **kwargs,
    )


def safe_delete_message(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.delete_message().
    """

    return safe_telegram_call(
        bot.delete_message,
        *args,
        **kwargs,
    )


def safe_send_photo(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.send_photo().
    """

    return safe_telegram_call(
        bot.send_photo,
        *args,
        **kwargs,
    )


def safe_send_document(
    bot: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Safe wrapper around bot.send_document().
    """

    return safe_telegram_call(
        bot.send_document,
        *args,
        **kwargs,
    )


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "MIN_REQUEST_INTERVAL",
    "MAX_RETRIES",
    "safe_telegram_call",
    "telegram_safe",
    "safe_send_message",
    "safe_reply_to",
    "safe_edit_message_text",
    "safe_delete_message",
    "safe_send_photo",
    "safe_send_document",
    "is_rate_limit_error",
]