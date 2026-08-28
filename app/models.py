from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(slots=True)
class ChatMessage:
    chat_id: int
    message_id: int
    user_id: int
    display_name: str
    timestamp: float
    text: str
    reply_to_message_id: int | None = None
    media_type: str | None = None
    image_file_id: str | None = None
    is_bot: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
