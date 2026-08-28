from __future__ import annotations
class ModerationActions:
    def can_restrict(self,member_status:str)->bool:return member_status in {"administrator","creator"}
