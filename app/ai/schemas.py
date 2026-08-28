from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
from app.chaos.actions import Action

@dataclass(slots=True)
class DecisionPayload:
    should_act: bool
    action: Action
    confidence: float
    target_message_id: int | None
    language: str
    dialect: str | None
    intensity: str

    @classmethod
    def validate(cls, data: dict[str,Any], valid_message_ids: set[int]) -> "DecisionPayload":
        action=Action(str(data.get("action","IGNORE")))
        conf=max(0,min(1,float(data.get("confidence",0))))
        target=data.get("target_message_id")
        if target is not None:
            target=int(target)
            if target not in valid_message_ids: target=None
        return cls(bool(data.get("should_act",False)),action,conf,target,str(data.get("language","unknown"))[:32],str(data.get("dialect"))[:64] if data.get("dialect") else None,str(data.get("intensity","low"))[:16])

DECISION_SCHEMA={"type":"object","properties":{"should_act":{"type":"boolean"},"action":{"type":"string"},"confidence":{"type":"number"},"target_message_id":{"type":["integer","null"]},"language":{"type":"string"},"dialect":{"type":["string","null"]},"intensity":{"type":"string"}},"required":["should_act","action","confidence","target_message_id","language","dialect","intensity"]}
