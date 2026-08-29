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
    media_type: str  # "photo" or "video"


class ImagePool:
    """
    Lightweight Telegram media pool.

    We store Telegram file_id only.
    No actual media files are kept on the server.
    """

    def __init__(
        self,
        ttl: float = 21600,
        max_per_chat: int = 50,
    ):
        self.ttl = max(
            60,
            float(ttl),
        )

        self.max = max(
            5,
            int(max_per_chat),
        )

        self.data: dict[int, list[ImageRef]] = {}

    # --------------------------------------------------
    # Add media
    # --------------------------------------------------

    def add(self, ref: ImageRef) -> None:
        q = self.data.setdefault(
            ref.chat_id,
            [],
        )

        # Avoid storing the exact same Telegram file twice.
        if any(
            x.telegram_file_id == ref.telegram_file_id
            for x in q
        ):
            return

        q.append(ref)

        self.cleanup(
            ref.chat_id
        )

        # Keep only the newest items.
        if len(q) > self.max:
            q = q[-self.max:]

        self.data[ref.chat_id] = q

    # --------------------------------------------------
    # Cleanup old media
    # --------------------------------------------------

    def cleanup(self, chat_id: int) -> None:
        now = time.time()
        cutoff = now - self.ttl

        q = self.data.get(
            chat_id,
            [],
        )

        self.data[chat_id] = [
            x
            for x in q
            if x.created_at >= cutoff
        ]

    # --------------------------------------------------
    # Choose random media
    # --------------------------------------------------

    def choose(
        self,
        chat_id: int,
        media_type: str | None = None,
        avoid_file_id: str | None = None,
    ) -> ImageRef | None:
        self.cleanup(chat_id)

        q = self.data.get(
            chat_id,
            [],
        )

        if not q:
            return None

        candidates = q

        # Optional photo/video filtering.
        if media_type:
            candidates = [
                x
                for x in candidates
                if x.media_type == media_type
            ]

        if not candidates:
            return None

        # Prefer unused media.
        unused = [
            x
            for x in candidates
            if x.used_at is None
        ]

        if unused:
            candidates = unused

        # Avoid immediately repeating the same file.
        if avoid_file_id:
            without_previous = [
                x
                for x in candidates
                if x.telegram_file_id != avoid_file_id
            ]

            if without_previous:
                candidates = without_previous

        return random.choice(
            candidates
        )

    # --------------------------------------------------
    # Choose specifically a photo
    # --------------------------------------------------

    def choose_photo(
        self,
        chat_id: int,
        avoid_file_id: str | None = None,
    ) -> ImageRef | None:
        return self.choose(
            chat_id,
            media_type="photo",
            avoid_file_id=avoid_file_id,
        )

    # --------------------------------------------------
    # Choose specifically a video
    # --------------------------------------------------

    def choose_video(
        self,
        chat_id: int,
        avoid_file_id: str | None = None,
    ) -> ImageRef | None:
        return self.choose(
            chat_id,
            media_type="video",
            avoid_file_id=avoid_file_id,
        )

    # --------------------------------------------------
    # Choose random photo or video
    # --------------------------------------------------

    def choose_random_media(
        self,
        chat_id: int,
        avoid_file_id: str | None = None,
    ) -> ImageRef | None:
        return self.choose(
            chat_id,
            media_type=None,
            avoid_file_id=avoid_file_id,
        )

    # --------------------------------------------------
    # Mark as used
    # --------------------------------------------------

    def mark_used(
        self,
        ref: ImageRef,
    ) -> None:
        ref.used_at = time.time()

    # --------------------------------------------------
    # Remove one item completely
    # --------------------------------------------------

    def remove(
        self,
        ref: ImageRef,
    ) -> None:
        q = self.data.get(
            ref.chat_id,
            [],
        )

        self.data[ref.chat_id] = [
            x
            for x in q
            if x.telegram_file_id
            != ref.telegram_file_id
        ]

    # --------------------------------------------------
    # Remove all used items
    # --------------------------------------------------

    def remove_used(
        self,
        chat_id: int,
    ) -> None:
        q = self.data.get(
            chat_id,
            [],
        )

        self.data[chat_id] = [
            x
            for x in q
            if x.used_at is None
        ]

    # --------------------------------------------------
    # Number of stored media
    # --------------------------------------------------

    def count(
        self,
        chat_id: int,
        media_type: str | None = None,
    ) -> int:
        self.cleanup(chat_id)

        q = self.data.get(
            chat_id,
            [],
        )

        if media_type:
            return sum(
                1
                for x in q
                if x.media_type == media_type
            )

        return len(q)

    # --------------------------------------------------
    # Clear a chat completely
    # --------------------------------------------------

    def clear(
        self,
        chat_id: int,
    ) -> None:
        self.data.pop(
            chat_id,
            None,
        )