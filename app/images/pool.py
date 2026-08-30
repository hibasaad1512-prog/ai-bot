from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class ImageRef:
    chat_id: int
    message_id: int
    telegram_file_id: str
    created_at: float
    used_at: float | None
    uploader_id: int
    media_type: str


class ImagePool:
    """Per-chat persistent Telegram media pool."""

    def __init__(self, ttl: float = 2592000, max_per_chat: int = 200, db=None):
        self.ttl = max(3600, float(ttl))
        self.max = max(20, int(max_per_chat))
        self.db = db
        self.data: dict[int, list[ImageRef]] = {}

    def _load(self, chat_id: int) -> None:
        if chat_id in self.data or self.db is None:
            return
        try:
            rows = self.db.list_media(chat_id, self.max)
            self.data[chat_id] = [ImageRef(**r) for r in rows]
        except Exception:
            self.data[chat_id] = []

    def add(self, ref: ImageRef) -> None:
        self._load(ref.chat_id)
        q = self.data.setdefault(ref.chat_id, [])
        if any(x.telegram_file_id == ref.telegram_file_id for x in q):
            return
        q.append(ref)
        self.cleanup(ref.chat_id)
        if len(q) > self.max:
            q = q[-self.max:]
        self.data[ref.chat_id] = q
        if self.db is not None:
            try:
                self.db.save_media(ref)
            except Exception:
                pass

    def cleanup(self, chat_id: int) -> None:
        self._load(chat_id)
        cutoff = time.time() - self.ttl
        q = [x for x in self.data.get(chat_id, []) if x.created_at >= cutoff]
        self.data[chat_id] = q

    def choose(self, chat_id: int, media_type: str | None = None, avoid_file_id: str | None = None) -> ImageRef | None:
        self._load(chat_id)
        self.cleanup(chat_id)
        candidates = self.data.get(chat_id, [])
        if media_type:
            candidates = [x for x in candidates if x.media_type == media_type]
        if not candidates:
            return None
        unused = [x for x in candidates if x.used_at is None]
        if unused:
            candidates = unused
        if avoid_file_id:
            without_previous = [x for x in candidates if x.telegram_file_id != avoid_file_id]
            if without_previous:
                candidates = without_previous
        return random.choice(candidates)

    def choose_photo(self, chat_id: int, avoid_file_id: str | None = None) -> ImageRef | None:
        return self.choose(chat_id, "photo", avoid_file_id)

    def choose_sticker(self, chat_id: int, avoid_file_id: str | None = None) -> ImageRef | None:
        return self.choose(chat_id, "sticker", avoid_file_id)

    def choose_video(self, chat_id: int, avoid_file_id: str | None = None) -> ImageRef | None:
        return self.choose(chat_id, "video", avoid_file_id)

    def choose_random_media(self, chat_id: int, avoid_file_id: str | None = None) -> ImageRef | None:
        return self.choose(chat_id, None, avoid_file_id)

    def mark_used(self, ref: ImageRef) -> None:
        ref.used_at = time.time()
        if self.db is not None:
            try:
                self.db.mark_media_used(ref.chat_id, ref.telegram_file_id, ref.used_at)
            except Exception:
                pass

    def remove(self, ref: ImageRef) -> None:
        self._load(ref.chat_id)
        self.data[ref.chat_id] = [x for x in self.data.get(ref.chat_id, []) if x.telegram_file_id != ref.telegram_file_id]
        if self.db is not None:
            try:
                self.db.delete_media(ref.chat_id, ref.telegram_file_id)
            except Exception:
                pass

    def remove_used(self, chat_id: int) -> None:
        self._load(chat_id)
        self.data[chat_id] = [x for x in self.data.get(chat_id, []) if x.used_at is None]
        if self.db is not None:
            try:
                self.db.delete_used_media(chat_id)
            except Exception:
                pass

    def count(self, chat_id: int, media_type: str | None = None) -> int:
        self._load(chat_id)
        self.cleanup(chat_id)
        q = self.data.get(chat_id, [])
        return sum(1 for x in q if not media_type or x.media_type == media_type)

    def clear(self, chat_id: int) -> None:
        self.data.pop(chat_id, None)
        if self.db is not None:
            try:
                self.db.clear_media(chat_id)
            except Exception:
                pass
