from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ============================================================
# Self Learning Memory
# ============================================================

class SelfLearningMemory:
    """
    Safe self-learning layer for الميرفاوية.

    It learns:
    - Basic facts about the group
    - Useful facts/preferences about users
    - Common words
    - Common phrases
    - Frequently used emojis
    - Emoji meaning/context
    - Conversation style
    - Lightweight user style
    - Topics and callbacks

    It does NOT modify Python source files.
    It stores learned information separately.
    """

    DEFAULT_PATH = "data/lmyrfawya_learning.json"

    # 😂 intentionally excluded.
    # 😹 is preferred for laughter.
    EMOJI_ALIASES = {
        "😂": "DISCOURAGED",
        "🤣": "DISCOURAGED",
        "😹": "LAUGH",
        "😭": "CRY_LAUGH",
        "💀": "DEAD_LAUGH",
        "😿": "SAD",
        "😾": "ANNOYED",
        "😼": "MISCHIEVOUS",
        "😻": "AFFECTION",
        "🥺": "SHY",
        "🙀": "SURPRISED",
        "👀": "CURIOUS",
        "❤️": "LOVE",
        "🔥": "HYPE",
        "🎀": "CUTE",
        "🐱": "CAT",
        "👍": "APPROVAL",
        "👏": "CLAP",
        "🤔": "THINKING",
        "😮": "SURPRISED",
        "😐": "NEUTRAL",
        "😭": "EMOTIONAL",
    }

    def __init__(
        self,
        path: str | None = None,
        max_users: int = 500,
        max_facts_per_user: int = 30,
        max_phrases_per_user: int = 40,
    ):
        self.path = Path(
            path
            or os.getenv(
                "SELF_LEARNING_PATH",
                self.DEFAULT_PATH,
            )
        )

        self.max_users = max(
            10,
            int(max_users),
        )

        self.max_facts_per_user = max(
            5,
            int(max_facts_per_user),
        )

        self.max_phrases_per_user = max(
            10,
            int(max_phrases_per_user),
        )

        self.data: dict[str, Any] = {
            "version": 1,
            "updated_at": time.time(),
            "groups": {},
        }

        self._load()

    # ========================================================
    # Storage
    # ========================================================

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return

            raw = self.path.read_text(
                encoding="utf-8"
            )

            loaded = json.loads(raw)

            if isinstance(loaded, dict):
                self.data = loaded

        except Exception:
            log.exception(
                "self-learning memory load failed"
            )

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            self.data["updated_at"] = time.time()

            temp_path = self.path.with_suffix(
                self.path.suffix + ".tmp"
            )

            temp_path.write_text(
                json.dumps(
                    self.data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            temp_path.replace(
                self.path
            )

        except Exception:
            log.exception(
                "self-learning memory save failed"
            )

    # ========================================================
    # Group helpers
    # ========================================================

    def _group(self, chat_id: int) -> dict[str, Any]:
        groups = self.data.setdefault(
            "groups",
            {},
        )

        key = str(chat_id)

        group = groups.setdefault(
            key,
            {
                "facts": [],
                "topics": Counter(),
                "words": Counter(),
                "phrases": Counter(),
                "emojis": Counter(),
                "emoji_contexts": {},
                "users": {},
                "last_learned": 0.0,
            },
        )

        return group

    def _user(
        self,
        chat_id: int,
        user_id: int,
    ) -> dict[str, Any]:

        group = self._group(chat_id)

        users = group.setdefault(
            "users",
            {},
        )

        key = str(user_id)

        return users.setdefault(
            key,
            {
                "name": "",
                "facts": [],
                "preferences": [],
                "words": Counter(),
                "phrases": Counter(),
                "emojis": Counter(),
                "style": {},
                "message_count": 0,
                "last_seen": 0.0,
            },
        )

    # ========================================================
    # Safe text extraction
    # ========================================================

    @staticmethod
    def _normalize(text: str) -> str:
        text = (
            text
            or ""
        ).strip()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    @staticmethod
    def _words(text: str) -> list[str]:
        return re.findall(
            r"\b[\wÀ-ÿ\u0600-\u06FF]+\b",
            text.lower(),
            flags=re.UNICODE,
        )

    @classmethod
    def _emoji_list(cls, text: str) -> list[str]:
        found = []

        for char in text:
            if char in cls.EMOJI_ALIASES:
                found.append(char)

        return found

    # ========================================================
    # Analyze a message
    # ========================================================

    def learn_message(
        self,
        chat_id: int,
        user_id: int,
        display_name: str,
        text: str,
    ) -> None:
        """
        Analyze one normal human message.
        """

        text = self._normalize(text)

        if not text:
            return

        group = self._group(chat_id)
        user = self._user(
            chat_id,
            user_id,
        )

        user["name"] = (
            display_name
            or user.get("name")
            or "user"
        )

        user["message_count"] = (
            int(user.get("message_count", 0)) + 1
        )

        user["last_seen"] = time.time()
        group["last_learned"] = time.time()

        # ----------------------------------------------------
        # Words
        # ----------------------------------------------------

        words = self._words(text)

        for word in words:
            if len(word) >= 2:
                self._counter_add(
                    user["words"],
                    word,
                )

                self._counter_add(
                    group["words"],
                    word,
                )

        # ----------------------------------------------------
        # Phrases
        # ----------------------------------------------------

        phrases = self._extract_phrases(
            text
        )

        for phrase in phrases:
            self._counter_add(
                user["phrases"],
                phrase,
            )

            self._counter_add(
                group["phrases"],
                phrase,
            )

        # ----------------------------------------------------
        # Emojis
        # ----------------------------------------------------

        emojis = self._emoji_list(text)

        for emoji in emojis:
            self._counter_add(
                user["emojis"],
                emoji,
            )

            self._counter_add(
                group["emojis"],
                emoji,
            )

            self._learn_emoji_context(
                group,
                emoji,
                text,
            )

        # ----------------------------------------------------
        # Basic style detection
        # ----------------------------------------------------

        style = user.setdefault(
            "style",
            {},
        )

        style["avg_message_length"] = self._running_average(
            style.get("avg_message_length"),
            len(text),
            user["message_count"],
        )

        style["emoji_rate"] = self._running_average(
            style.get("emoji_rate"),
            len(emojis),
            user["message_count"],
        )

        style["question_rate"] = self._running_average(
            style.get("question_rate"),
            1 if "?" in text or "؟" in text else 0,
            user["message_count"],
        )

        style["exclamation_rate"] = self._running_average(
            style.get("exclamation_rate"),
            1 if "!" in text or "！" in text else 0,
            user["message_count"],
        )

        # ----------------------------------------------------
        # Detect basic facts/preferences
        # ----------------------------------------------------

        self._learn_basic_facts(
            group,
            user,
            text,
        )

        # Keep storage under control.
        self._trim_group(
            group
        )

        self._save()

    # ========================================================
    # Counter helpers
    # ========================================================

    @staticmethod
    def _counter_add(
        counter: Any,
        key: str,
        amount: int = 1,
    ) -> None:

        if not isinstance(
            counter,
            dict,
        ):
            return

        counter[key] = (
            int(counter.get(key, 0))
            + amount
        )

    @staticmethod
    def _running_average(
        old: float | None,
        new_value: float,
        count: int,
    ) -> float:

        if not old or count <= 1:
            return float(new_value)

        return (
            (float(old) * (count - 1))
            + new_value
        ) / count

    # ========================================================
    # Phrase extraction
    # ========================================================

    @staticmethod
    def _extract_phrases(
        text: str,
    ) -> list[str]:

        words = text.split()

        if len(words) < 2:
            return []

        phrases: list[str] = []

        for size in (
            2,
            3,
            4,
        ):
            if len(words) < size:
                continue

            # Only a few phrases per message.
            limit = min(
                len(words) - size + 1,
                5,
            )

            for index in range(limit):
                phrase = " ".join(
                    words[index:index + size]
                ).strip()

                if (
                    2 <= len(phrase) <= 80
                ):
                    phrases.append(
                        phrase.lower()
                    )

        return phrases

    # ========================================================
    # Emoji analysis
    # ========================================================

    def _learn_emoji_context(
        self,
        group: dict[str, Any],
        emoji: str,
        text: str,
    ) -> None:

        contexts = group.setdefault(
            "emoji_contexts",
            {},
        )

        entry = contexts.setdefault(
            emoji,
            {
                "count": 0,
                "labels": Counter(),
            },
        )

        entry["count"] = (
            int(entry.get("count", 0)) + 1
        )

        label = self.EMOJI_ALIASES.get(
            emoji,
            "OTHER",
        )

        labels = entry.setdefault(
            "labels",
            {},
        )

        self._counter_add(
            labels,
            label,
        )

    # ========================================================
    # Basic fact learning
    # ========================================================

    def _learn_basic_facts(
        self,
        group: dict[str, Any],
        user: dict[str, Any],
        text: str,
    ) -> None:

        lower = text.lower()

        patterns = [
            (
                r"\b(?:i|i'm|i am|my name is)\s+(.{2,80})",
                "statement",
            ),
            (
                r"(?:اسمي|انا اسمي|أنا اسمي)\s+(.{2,80})",
                "name",
            ),
            (
                r"(?:احب|أحب|يعجبني|كنحب|كنبغي)\s+(.{2,80})",
                "likes",
            ),
            (
                r"(?:ما احب|ما أحب|مبغيش|ما كنحبش)\s+(.{2,80})",
                "dislikes",
            ),
        ]

        for pattern, kind in patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            value = self._normalize(
                match.group(1)
            )

            value = value.strip(
                ".,!?؟،:;\"' "
            )

            if (
                not value
                or len(value) > 100
            ):
                continue

            facts = user.setdefault(
                "facts",
                [],
            )

            item = {
                "type": kind,
                "value": value,
                "confidence": 0.65,
                "updated_at": time.time(),
            }

            # Avoid duplicate facts.
            duplicate = any(
                str(x.get("type")) == kind
                and str(x.get("value")).lower()
                == value.lower()
                for x in facts
            )

            if not duplicate:
                facts.append(item)

        self._trim_list(
            user.setdefault(
                "facts",
                [],
            ),
            self.max_facts_per_user,
        )

    # ========================================================
    # Trimming
    # ========================================================

    def _trim_group(
        self,
        group: dict[str, Any],
    ) -> None:

        users = group.get(
            "users",
            {},
        )

        if (
            len(users)
            > self.max_users
        ):
            ordered = sorted(
                users.items(),
                key=lambda item:
                float(
                    item[1].get(
                        "last_seen",
                        0,
                    )
                ),
                reverse=True,
            )

            group["users"] = dict(
                ordered[:self.max_users]
            )

        self._trim_counter(
            group.get("words", {})
        )

        self._trim_counter(
            group.get("phrases", {})
        )

        self._trim_counter(
            group.get("emojis", {})
        )

        for user in group.get(
            "users",
            {},
        ).values():

            self._trim_counter(
                user.get("words", {})
            )

            self._trim_counter(
                user.get("phrases", {})
            )

            self._trim_counter(
                user.get("emojis", {})
            )

            self._trim_list(
                user.get("facts", []),
                self.max_facts_per_user,
            )

    @staticmethod
    def _trim_counter(
        counter: dict[str, int],
        maximum: int = 100,
    ) -> None:

        if not isinstance(
            counter,
            dict,
        ):
            return

        if len(counter) <= maximum:
            return

        items = sorted(
            counter.items(),
            key=lambda item: int(item[1]),
            reverse=True,
        )[:maximum]

        counter.clear()
        counter.update(items)

    @staticmethod
    def _trim_list(
        items: list[Any],
        maximum: int,
    ) -> None:

        if len(items) <= maximum:
            return

        del items[:-maximum]

    # ========================================================
    # Public learning APIs
    # ========================================================

    def remember_fact(
        self,
        chat_id: int,
        user_id: int,
        fact: str,
        fact_type: str = "fact",
        confidence: float = 0.8,
    ) -> None:

        user = self._user(
            chat_id,
            user_id,
        )

        facts = user.setdefault(
            "facts",
            [],
        )

        fact = self._normalize(
            fact
        )

        if not fact:
            return

        duplicate = any(
            str(x.get("value")).lower()
            == fact.lower()
            for x in facts
        )

        if duplicate:
            return

        facts.append(
            {
                "type": fact_type,
                "value": fact,
                "confidence": max(
                    0.0,
                    min(1.0, float(confidence)),
                ),
                "updated_at": time.time(),
            }
        )

        self._trim_list(
            facts,
            self.max_facts_per_user,
        )

        self._save()

    def remember_group_fact(
        self,
        chat_id: int,
        fact: str,
        fact_type: str = "group_fact",
        confidence: float = 0.8,
    ) -> None:

        group = self._group(
            chat_id
        )

        facts = group.setdefault(
            "facts",
            [],
        )

        fact = self._normalize(
            fact
        )

        if not fact:
            return

        duplicate = any(
            str(x.get("value")).lower()
            == fact.lower()
            for x in facts
        )

        if duplicate:
            return

        facts.append(
            {
                "type": fact_type,
                "value": fact,
                "confidence": max(
                    0.0,
                    min(1.0, float(confidence)),
                ),
                "updated_at": time.time(),
            }
        )

        self._trim_list(
            facts,
            50,
        )

        self._save()

    # ========================================================
    # Retrieval for prompts
    # ========================================================

    def get_user_memory(
        self,
        chat_id: int,
        user_id: int,
    ) -> dict[str, Any]:

        user = self._user(
            chat_id,
            user_id,
        )

        return {
            "name": user.get(
                "name",
                "",
            ),
            "facts": user.get(
                "facts",
                [],
            )[-self.max_facts_per_user:],
            "preferences": user.get(
                "preferences",
                [],
            ),
            "top_words": self._top_counter(
                user.get("words", {}),
                15,
            ),
            "top_phrases": self._top_counter(
                user.get("phrases", {}),
                10,
            ),
            "frequent_emojis": self._top_counter(
                user.get("emojis", {}),
                10,
            ),
            "style": user.get(
                "style",
                {},
            ),
            "message_count": int(
                user.get(
                    "message_count",
                    0,
                )
            ),
        }

    def get_group_memory(
        self,
        chat_id: int,
    ) -> dict[str, Any]:

        group = self._group(
            chat_id
        )

        return {
            "facts": group.get(
                "facts",
                [],
            )[-30:],
            "top_words": self._top_counter(
                group.get("words", {}),
                20,
            ),
            "top_phrases": self._top_counter(
                group.get("phrases", {}),
                15,
            ),
            "frequent_emojis": self._top_counter(
                group.get("emojis", {}),
                15,
            ),
            "emoji_contexts": self._emoji_summary(
                group.get(
                    "emoji_contexts",
                    {},
                )
            ),
        }

    # ========================================================
    # Emoji preference
    # ========================================================

    def preferred_emojis(
        self,
        chat_id: int,
        limit: int = 6,
    ) -> list[str]:

        group = self._group(
            chat_id
        )

        counter = group.get(
            "emojis",
            {},
        )

        items = sorted(
            counter.items(),
            key=lambda item: int(item[1]),
            reverse=True,
        )

        output: list[str] = []

        for emoji, _count in items:
            # 😂 should not become a preferred emoji.
            if emoji in {
                "😂",
                "🤣",
            }:
                continue

            output.append(emoji)

            if len(output) >= limit:
                break

        # Make 😹 available as the preferred laughter emoji.
        if "😹" not in output:
            output.append("😹")

        return output[:limit]

    # ========================================================
    # Prompt summary
    # ========================================================

    def prompt_summary(
        self,
        chat_id: int,
        user_id: int | None = None,
    ) -> str:

        group_memory = self.get_group_memory(
            chat_id
        )

        lines = [
            "SELF-LEARNED GROUP MEMORY:",
            json.dumps(
                group_memory,
                ensure_ascii=False,
            ),
        ]

        if user_id is not None:
            user_memory = self.get_user_memory(
                chat_id,
                user_id,
            )

            lines.extend(
                [
                    "",
                    "SELF-LEARNED USER MEMORY:",
                    json.dumps(
                        user_memory,
                        ensure_ascii=False,
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "EMOJI RULE:",
                "Do not use 😂 or 🤣 for laughter.",
                "Prefer 😹 when a laughter emoji genuinely fits.",
                "Emojis are optional.",
                "Do not spam emojis.",
            ]
        )

        return "\n".join(
            lines
        )

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _top_counter(
        counter: dict[str, int],
        limit: int,
    ) -> list[dict[str, Any]]:

        if not isinstance(
            counter,
            dict,
        ):
            return []

        return [
            {
                "value": key,
                "count": int(value),
            }
            for key, value in sorted(
                counter.items(),
                key=lambda item: int(item[1]),
                reverse=True,
            )[:limit]
        ]

    @staticmethod
    def _emoji_summary(
        contexts: dict[str, Any],
    ) -> dict[str, Any]:

        result = {}

        for emoji, data in contexts.items():
            result[emoji] = {
                "count": int(
                    data.get(
                        "count",
                        0,
                    )
                ),
                "meaning": SelfLearningMemory.EMOJI_ALIASES.get(
                    emoji,
                    "OTHER",
                ),
                "labels": data.get(
                    "labels",
                    {},
                ),
            }

        return result

    # ========================================================
    # Export / reset
    # ========================================================

    def export(
        self,
        chat_id: int,
    ) -> dict[str, Any]:

        group = self._group(
            chat_id
        )

        return {
            "chat_id": chat_id,
            "memory": group,
        }

    def clear_user(
        self,
        chat_id: int,
        user_id: int,
    ) -> None:

        group = self._group(
            chat_id
        )

        users = group.setdefault(
            "users",
            {},
        )

        users.pop(
            str(user_id),
            None,
        )

        self._save()

    def clear_group(
        self,
        chat_id: int,
    ) -> None:

        groups = self.data.setdefault(
            "groups",
            {},
        )

        groups.pop(
            str(chat_id),
            None,
        )

        self._save()