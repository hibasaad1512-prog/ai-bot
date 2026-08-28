from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

class Action(str, Enum):
    IGNORE="IGNORE"; REPLY_CONTEXT="REPLY_CONTEXT"; JOIN_CONVERSATION="JOIN_CONVERSATION"; CHAOS_TEXT="CHAOS_TEXT"
    REACTION="REACTION"; OLD_MESSAGE_REACT="OLD_MESSAGE_REACT"; QUOTE_REMIX="QUOTE_REMIX"; RANDOM_MEMBER_INTERACTION="RANDOM_MEMBER_INTERACTION"
    RANDOM_IMAGE="RANDOM_IMAGE"; IMAGE_CAPTION="IMAGE_CAPTION"; IMAGE_MASHUP="IMAGE_MASHUP"; COLLAGE="COLLAGE"; CONTEXT_MEME="CONTEXT_MEME"
    GENERATE_IMAGE="GENERATE_IMAGE"; RANDOM_TEMPLATE="RANDOM_TEMPLATE"; FAKE_ANNOUNCEMENT="FAKE_ANNOUNCEMENT"; POLL="POLL"; CHAOS_EVENT="CHAOS_EVENT"
    STICKER_REACTION="STICKER_REACTION"; COMPANION_BOT="COMPANION_BOT"; TOPIC_CALLBACK="TOPIC_CALLBACK"; RANDOM_QUESTION="RANDOM_QUESTION"; MINI_CHALLENGE="MINI_CHALLENGE"

@dataclass(frozen=True, slots=True)
class ActionSpec:
    weight: float
    min_score: float
    cooldown: float
    handler: str

DEFAULT_ACTIONS = {
    Action.IGNORE: ActionSpec(45, 0, 10, "ignore"),
    Action.REPLY_CONTEXT: ActionSpec(16, 48, 35, "reply_context"),
    Action.JOIN_CONVERSATION: ActionSpec(8, 55, 45, "reply_context"),
    Action.CHAOS_TEXT: ActionSpec(7, 60, 60, "chaos_text"),
    Action.OLD_MESSAGE_REACT: ActionSpec(5, 65, 180, "old_message"),
    Action.REACTION: ActionSpec(4, 45, 45, "reaction"),
    Action.RANDOM_IMAGE: ActionSpec(3, 62, 90, "random_image"),
    Action.IMAGE_CAPTION: ActionSpec(3, 65, 120, "image_caption"),
    Action.IMAGE_MASHUP: ActionSpec(2, 72, 180, "image_mashup"),
    Action.GENERATE_IMAGE: ActionSpec(1.5, 82, 300, "generate_image"),
    Action.CHAOS_EVENT: ActionSpec(1.5, 80, 600, "chaos_event"),
    Action.QUOTE_REMIX: ActionSpec(1, 68, 180, "quote_remix"),
    Action.RANDOM_MEMBER_INTERACTION: ActionSpec(1, 65, 180, "member_interaction"),
    Action.CONTEXT_MEME: ActionSpec(1, 68, 180, "context_meme"),
    Action.RANDOM_QUESTION: ActionSpec(1, 60, 120, "random_question"),
    Action.MINI_CHALLENGE: ActionSpec(1, 72, 240, "mini_challenge"),
    Action.POLL: ActionSpec(0.5, 75, 300, "poll"),
    Action.FAKE_ANNOUNCEMENT: ActionSpec(0.4, 88, 900, "fake_announcement"),
    Action.RANDOM_TEMPLATE: ActionSpec(0.5, 75, 240, "chaos_text"),
    Action.STICKER_REACTION: ActionSpec(0.5, 72, 180, "reaction"),
    Action.COLLAGE: ActionSpec(0.5, 78, 300, "image_mashup"),
    Action.COMPANION_BOT: ActionSpec(0.1, 92, 900, "companion"),
    Action.TOPIC_CALLBACK: ActionSpec(1, 70, 300, "old_message"),
}

class ActionRegistry:
    def __init__(self): self._handlers: dict[str, Callable[..., Any]] = {}
    def register(self, name: str, handler: Callable[..., Any]) -> None: self._handlers[name] = handler
    def get(self, name: str) -> Callable[..., Any] | None: return self._handlers.get(name)
