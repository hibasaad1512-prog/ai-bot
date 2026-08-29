from __future__ import annotations


def is_non_command_message(message) -> bool:
    """Return True only for messages that belong to the normal AI/media path."""
    if not getattr(message, "from_user", None):
        return False

    text = (
        getattr(message, "text", None)
        or getattr(message, "caption", None)
        or ""
    )

    if text.strip():
        return not text.lstrip().startswith("/")

    # Media-only messages are still routed so their file_id can be
    # collected into the per-chat media pool.
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "sticker", None)
    )
