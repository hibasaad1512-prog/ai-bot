from __future__ import annotations
from dataclasses import dataclass
from .rules import ModerationPolicy
@dataclass(slots=True)
class ModerationResult:
    action:str; reason:str
class ModerationDetector:
    def __init__(self,policy:ModerationPolicy):self.policy=policy
    def detect(self,text:str,recent:list[str])->ModerationResult|None:
        x=self.policy.inspect(text,recent); return ModerationResult(*x) if x else None
