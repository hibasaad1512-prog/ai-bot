from __future__ import annotations

import time
from collections import deque

from app.models import ChatMessage
from app.ai.privacy import sanitize_for_ai, anonymized_speaker


class ContextStore:
    def __init__(self, maxlen: int = 40, ttl: float = 7200, db=None):
        self.maxlen = maxlen
        self.ttl = ttl
        self.db = db
        self._data: dict[int, deque[ChatMessage]] = {}

    def _hydrate(self, chat_id: int) -> None:
        if chat_id in self._data or self.db is None:
            return
        try:
            rows = self.db.recent_messages(chat_id, self.maxlen)
            if rows:
                q = deque(rows, maxlen=self.maxlen)
                self._data[chat_id] = q
                self._trim(chat_id)
        except Exception:
            pass

    def add(self, m: ChatMessage) -> None:
        q = self._data.setdefault(m.chat_id, deque(maxlen=self.maxlen))
        q.append(m)
        self._trim(m.chat_id)
        if self.db is not None:
            try:
                self.db.save_message(m)
            except Exception:
                # Database persistence must never break Telegram replies.
                pass

    def recent(self, chat_id: int, limit: int | None = None) -> list[ChatMessage]:
        self._hydrate(chat_id)
        self._trim(chat_id)
        q = list(self._data.get(chat_id, ()))
        return q[-limit:] if limit else q

    def _trim(self, chat_id: int) -> None:
        q = self._data.get(chat_id)
        if not q:
            return
        now = time.time()
        while q and now - q[0].timestamp > self.ttl:
            q.popleft()
        if not q:
            self._data.pop(chat_id, None)

    def text(self, chat_id: int, limit: int = 20) -> str:
        now = time.time()
        rows = []
        for m in self.recent(chat_id, limit):
            if not m.text:
                continue
            safe = sanitize_for_ai(m.text)
            age = max(0, int(now - m.timestamp))
            reply = f" reply_to={m.reply_to_message_id}" if m.reply_to_message_id else ""
            media = f" media={m.media_type}" if m.media_type else ""
            speaker = self._speaker(m)
            rows.append(f"[{m.message_id} age={age}s{reply}{media}] {speaker}: {safe.text}")
        return "\n".join(rows)

    @staticmethod
    def _speaker(m: ChatMessage) -> str:
        if m.is_bot:
            return "lmyrfawya"
        return anonymized_speaker(m.user_id)
