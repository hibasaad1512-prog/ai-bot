from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass


SECRET_PATTERNS = [
    re.compile(
        r"\bgsk_[A-Za-z0-9_-]{12,}\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:api[_ -]?key|token|secret|access[_ -]?token|authorization|bearer)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:password|passwd|pwd|passcode|otp|2fa)\s*[:=]?\s*\S+",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b(?:https?://|www\.)\S+",
        re.IGNORECASE,
    ),

    re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
    ),
]


SENSITIVE_PATTERNS = [
    re.compile(
        r"(?:porn|porno|xxx|sex video|nude|nudes|explicit sex|"
        r"blowjob|handjob|deepthroat|anal sex|oral sex)",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:اباحي|إباحي|جنس صريح|ممارسة الجنس|علاقة جنسية|"
        r"عاري(?:ة)?|صور عارية|فيديو جنسي|استمناء|جماع|سكس|"
        r"نيك|شرموط|قحبة|مضاجعة)",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:suicide|kill myself|self[- ]harm|cut myself|want to die)",
        re.IGNORECASE,
    ),

    re.compile(
        r"(?:انتحار|أنتحر|قتل نفسي|إيذاء نفسي|أؤذي نفسي|أريد الموت)",
        re.IGNORECASE,
    ),

    re.compile(
        r"\bsexual\b",
        re.IGNORECASE,
    ),

    re.compile(
        r"\bsex(?:ual)?\s+topic\b",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True, slots=True)
class PrivacyResult:
    text: str
    sensitive: bool
    redacted: bool


class PrivacyFilter:
    SENSITIVE_MARKER = "[REDACTED SENSITIVE TOPIC]"
    PRIVATE_MARKER = "[PRIVATE_DATA_REDACTED]"

    @staticmethod
    def _redact_secrets(
        text: str,
    ) -> tuple[str, bool]:

        if not text:
            return "", False

        changed = False
        cleaned = str(text)

        for pattern in SECRET_PATTERNS:
            cleaned, count = pattern.subn(
                PrivacyFilter.PRIVATE_MARKER,
                cleaned,
            )

            if count:
                changed = True

        return cleaned, changed

    @staticmethod
    def is_sensitive(
        text: str,
    ) -> bool:

        if not text:
            return False

        return any(
            pattern.search(str(text))
            for pattern in SENSITIVE_PATTERNS
        )

    @staticmethod
    def sanitize(
        text: str,
    ) -> PrivacyResult:

        if not text:
            return PrivacyResult(
                "",
                False,
                False,
            )

        text = str(text).strip()

        if PrivacyFilter.is_sensitive(text):
            return PrivacyResult(
                PrivacyFilter.SENSITIVE_MARKER,
                True,
                True,
            )

        cleaned, redacted = (
            PrivacyFilter._redact_secrets(text)
        )

        cleaned = cleaned.strip()[:700]

        return PrivacyResult(
            cleaned,
            False,
            redacted,
        )

    @staticmethod
    def sanitize_for_ai(
        text: str,
    ) -> str:

        return PrivacyFilter.sanitize(
            text
        ).text

    @staticmethod
    def non_verbatim(
        text: str,
        max_terms: int = 4,
        seed: int | None = None,
    ) -> str:

        result = PrivacyFilter.sanitize(
            text
        )

        if result.sensitive or not result.text:
            return ""

        words = re.findall(
            r"\S+",
            result.text,
        )

        if not words:
            return ""

        if len(words) == 1:
            return (
                f"keywords: {words[0]}"
            )

        rng = random.Random(
            seed
        )

        count = min(
            max(2, max_terms),
            len(words),
        )

        chosen = rng.sample(
            words,
            count,
        )

        rng.shuffle(
            chosen
        )

        return (
            "keywords: "
            + " ".join(chosen)
        )

    @staticmethod
    def anonymized_speaker(
        user_id: int,
    ) -> str:

        digest = hashlib.sha256(
            str(user_id).encode("utf-8")
        ).hexdigest()[:6]

        return f"User-{digest}"


def sanitize_for_ai(
    text: str,
) -> str:

    return PrivacyFilter.sanitize_for_ai(
        text
    )


def non_verbatim(
    text: str,
    max_terms: int = 4,
    seed: int | None = None,
) -> str:

    return PrivacyFilter.non_verbatim(
        text,
        max_terms=max_terms,
        seed=seed,
    )


def is_sensitive(
    text: str,
) -> bool:

    return PrivacyFilter.is_sensitive(
        text
    )


def anonymized_speaker(
    user_id: int,
) -> str:

    return PrivacyFilter.anonymized_speaker(
        user_id
    )