from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass


# =========================================================
# SECRET / PRIVATE DATA PATTERNS
# =========================================================

_SECRET_PATTERNS = [
    # Groq / common API keys
    re.compile(
        r"\bgsk_[A-Za-z0-9_-]{12,}\b",
        re.I,
    ),

    # Generic key/token/secret assignments
    re.compile(
        r"\b(?:api[_ -]?key|token|secret|access[_ -]?token|"
        r"authorization|bearer)\s*[:=]\s*\S+",
        re.I,
    ),

    # Password-like assignments
    re.compile(
        r"\b(?:password|passwd|pwd|passcode|otp|2fa)\s*[:=]?\s*\S+",
        re.I,
    ),

    # URLs
    re.compile(
        r"\b(?:https?://|www\.)\S+",
        re.I,
    ),

    # Email addresses
    re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.I,
    ),

    # Phone-like numbers
    re.compile(
        r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
    ),
]


# =========================================================
# SENSITIVE CONTENT
# =========================================================
#
# This is for privacy/data-minimization.
# It is NOT intended to bypass provider safety controls.
#

_SENSITIVE_PATTERNS = [
    re.compile(
        r"(?:"
        r"porn|porno|xxx|sex video|nude|nudes|"
        r"explicit sex|blowjob|handjob|deepthroat|"
        r"anal sex|oral sex"
        r")",
        re.I,
    ),

    re.compile(
        r"(?:"
        r"اباحي|إباحي|جنس صريح|ممارسة الجنس|"
        r"علاقة جنسية|عاري(?:ة)?|صور عارية|"
        r"فيديو جنسي|استمناء|جماع|سكس|نيك|"
        r"شرموط|قحبة|مضاجعة"
        r")",
        re.I,
    ),

    re.compile(
        r"(?:"
        r"suicide|kill myself|self[- ]harm|"
        r"cut myself|want to die"
        r")",
        re.I,
    ),

    re.compile(
        r"(?:"
        r"انتحار|أنتحر|قتل نفسي|إيذاء نفسي|"
        r"أؤذي نفسي|أريد الموت"
        r")",
        re.I,
    ),

    re.compile(
        r"\bsexual\b",
        re.I,
    ),

    re.compile(
        r"\bsex(?:ual)?\s+topic\b",
        re.I,
    ),
]


# =========================================================
# RESULT
# =========================================================

@dataclass(frozen=True, slots=True)
class PrivacyResult:
    text: str
    sensitive: bool
    redacted: bool


# =========================================================
# PRIVACY FILTER
# =========================================================

class PrivacyFilter:
    """
    Local privacy boundary used before text enters an AI prompt.

    Responsibilities:
    - Remove obvious secrets and private contact data.
    - Detect explicitly sensitive content.
    - Produce a safe redacted representation.
    - Produce non-verbatim context for random callbacks/remixes.
    - Provide stable anonymized speaker labels.
    """

    SENSITIVE_MARKER = "[REDACTED SENSITIVE TOPIC]"
    PRIVATE_MARKER = "[PRIVATE_DATA_REDACTED]"

    # -----------------------------------------------------
    # SECRET REDACTION
    # -----------------------------------------------------

    @staticmethod
    def _redact_secrets(
        text: str,
    ) -> tuple[str, bool]:

        if not text:
            return "", False

        changed = False
        out = text

        for pattern in _SECRET_PATTERNS:
            out, count = pattern.subn(
                PrivacyFilter.PRIVATE_MARKER,
                out,
            )

            if count:
                changed = True

        return out, changed

    # -----------------------------------------------------
    # SENSITIVE CHECK
    # -----------------------------------------------------

    @staticmethod
    def is_sensitive(
        text: str,
    ) -> bool:

        if not text:
            return False

        return any(
            pattern.search(text)
            for pattern in _SENSITIVE_PATTERNS
        )

    # -----------------------------------------------------
    # SANITIZE
    # -----------------------------------------------------

    @staticmethod
    def sanitize(
        text: str,
    ) -> PrivacyResult:

        if not text:
            return PrivacyResult(
                text="",
                sensitive=False,
                redacted=False,
            )

        # Sensitive content is not forwarded verbatim.
        if PrivacyFilter.is_sensitive(text):

            return PrivacyResult(
                text=PrivacyFilter.SENSITIVE_MARKER,
                sensitive=True,
                redacted=True,
            )

        cleaned, redacted = (
            PrivacyFilter._redact_secrets(text)
        )

        # Limit the amount of text entering prompts.
        cleaned = cleaned.strip()[:700]

        return PrivacyResult(
            text=cleaned,
            sensitive=False,
            redacted=redacted,
        )

    # -----------------------------------------------------
    # API-FACING HELPER
    # -----------------------------------------------------

    @staticmethod
    def sanitize_for_ai(
        text: str,
    ) -> str:
        """
        Return only the privacy-sanitized representation
        intended for use inside an AI prompt.

        Sensitive content is replaced rather than forwarded
        verbatim.
        """

        result = PrivacyFilter.sanitize(
            text
        )

        return result.text

    # -----------------------------------------------------
    # NON-VERBATIM CONTEXT
    # -----------------------------------------------------

    @staticmethod
    def non_verbatim(
        text: str,
        max_terms: int = 4,
        seed: int | None = None,
    ) -> str:

        result = PrivacyFilter.sanitize(
            text
        )

        # Never recycle sensitive content.
        if result.sensitive:
            return ""

        if not result.text:
            return ""

        words = re.findall(
            r"\S+",
            result.text,
        )

        if not words:
            return ""

        if len(words) == 1:
            return (
                "keywords: "
                + words[0]
            )

        rng = random.Random(
            seed
        )

        count = min(
            max(
                2,
                max_terms,
            ),
            len(words),
        )

        # Select unrelated terms and shuffle them.
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

    # -----------------------------------------------------
    # ANONYMIZED SPEAKER
    # -----------------------------------------------------

    @staticmethod
    def anonymized_speaker(
        user_id: int,
    ) -> str:

        digest = hashlib.sha256(
            str(user_id).encode()
        ).hexdigest()[:6]

        return (
            f"User-{digest}"
        )


# =========================================================
# MODULE-LEVEL COMPATIBILITY HELPERS
# =========================================================

def sanitize_for_ai(
    text: str,
) -> str:
    """
    Compatibility helper.

    Allows existing code to use:

        from app.ai.privacy import sanitize_for_ai
    """

    return PrivacyFilter.sanitize_for_ai(
        text
    )


def non_verbatim(
    text: str,
    max_terms: int = 4,
    seed: int | None = None,
) -> str:
    """
    Module-level compatibility wrapper.
    """

    return PrivacyFilter.non_verbatim(
        text,
        max_terms=max_terms,
        seed=seed,
    )


def is_sensitive(
    text: str,
) -> bool:
    """
    Module-level compatibility wrapper.
    """

    return PrivacyFilter.is_sensitive(
        text
    )