from __future__ import annotations


def is_non_command_message(message) -> bool:
    """Return True only for messages that belong to the normal AI path."""
    if not getattr(message, "from_user", None):
        return False
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    if not text.strip():
        return bool(getattr(message, "photo", None))
    return not text.lstrip().startswith("/")
