from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

_SECRET_PATTERNS = [
    re.compile(r"\bgsk_[A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"\b(?:sk|pk|rk|api|token|secret)[_-]?\s*[:=]\s*\S+", re.I),
    re.compile(r"\b(?:password|passwd|pwd|passcode|otp|2fa)\s*[:=]?\s*\S+", re.I),
    re.compile(r"\b(?:https?://|www\.)\S+", re.I),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"),
]

# Explicit content only. Ordinary historical, educational, or medical text is
# not automatically blocked unless it contains clearly explicit terminology.
_SENSITIVE_PATTERNS = [
    re.compile(r"(?:porn|porno|xxx|sex video|nude|nudes|explicit sex|blowjob|handjob|deepthroat|anal sex|oral sex)", re.I),
    re.compile(r"(?:اباحي|إباحي|جنس صريح|ممارسة الجنس|علاقة جنسية|عاري(?:ة)?|صور عارية|فيديو جنسي|استمناء|جماع|سكس|نيك|زب|كس|شرموط|قحبة|مضاجعة)", re.I),
    re.compile(r"(?:suicide|kill myself|self[- ]harm|cut myself|want to die)", re.I),
    re.compile(r"(?:انتحار|أنتحر|قتل نفسي|إيذاء نفسي|أؤذي نفسي|أريد الموت)", re.I),
    re.compile(r"\bsexual\b", re.I),
    re.compile(r"\bsex(?:ual)?\s+topic\b", re.I),
]

@dataclass(frozen=True, slots=True)
class PrivacyResult:
    text: str
    sensitive: bool
    redacted: bool

class PrivacyFilter:
    """Local privacy boundary used before data enters an AI prompt."""

    SENSITIVE_MARKER = "[REDACTED SENSITIVE TOPIC]"
    PRIVATE_MARKER = "[PRIVATE_DATA_REDACTED]"

    @staticmethod
    def _redact_secrets(text: str) -> tuple[str, bool]:
        changed = False
        out = text
        for pattern in _SECRET_PATTERNS:
            out, n = pattern.subn(PrivacyFilter.PRIVATE_MARKER, out)
            changed = changed or bool(n)
        return out, changed

    @staticmethod
    def is_sensitive(text: str) -> bool:
        return bool(text) and any(p.search(text) for p in _SENSITIVE_PATTERNS)

    @staticmethod
    def sanitize(text: str) -> PrivacyResult:
        if not text:
            return PrivacyResult("", False, False)
        if PrivacyFilter.is_sensitive(text):
            return PrivacyResult(PrivacyFilter.SENSITIVE_MARKER, True, True)
        cleaned, redacted = PrivacyFilter._redact_secrets(text)
        # A secret/contact detail is also considered sensitive for learning:
        # it must not be learned or used as a normal context signal.
        return PrivacyResult(cleaned[:700], redacted, redacted)

    @staticmethod
    def non_verbatim(text: str, max_terms: int = 4, seed: int | None = None) -> str:
        result = PrivacyFilter.sanitize(text)
        if result.sensitive:
            return ""
        words = re.findall(r"\S+", result.text)
        if not words:
            return ""
        if len(words) == 1:
            return "keywords: " + words[0]
        rng = random.Random(seed)
        count = min(max(2, max_terms), len(words))
        # Shuffle selected words so the original sentence cannot be quoted.
        chosen = rng.sample(words, count)
        rng.shuffle(chosen)
        return "keywords: " + " ".join(chosen)

    @staticmethod
    def anonymized_speaker(user_id: int) -> str:
        digest = hashlib.sha256(str(user_id).encode()).hexdigest()[:6]
        return f"User-{digest}"
