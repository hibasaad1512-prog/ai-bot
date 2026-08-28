from __future__ import annotations
import os
from dataclasses import dataclass, field


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def env_ids(name: str) -> frozenset[int]:
    out: set[int] = set()
    for raw in os.getenv(name, "").split(","):
        raw = raw.strip()
        if raw:
            try:
                out.add(int(raw))
            except ValueError:
                pass
    return frozenset(out)


@dataclass(frozen=True)
class PersonalityDefaults:
    chaos: int = env_int("DEFAULT_CHAOS", 70, 0)
    humor: int = env_int("DEFAULT_HUMOR", 75, 0)
    social: int = env_int("DEFAULT_SOCIAL", 80, 0)
    weirdness: int = env_int("DEFAULT_WEIRDNESS", 55, 0)
    images: int = env_int("DEFAULT_IMAGES", 65, 0)
    events: int = env_int("DEFAULT_EVENTS", 50, 0)
    roast: int = env_int("DEFAULT_ROAST", 25, 0)
    emoji: int = env_int("DEFAULT_EMOJI", 20, 0)
    human_imperfection: int = env_int("DEFAULT_HUMAN_IMPERFECTION", 70, 0)
    proactivity: int = env_int("DEFAULT_PROACTIVITY", 65, 0)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    # Optional external DB. Empty means local SQLite on the Render instance.
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    # Prefer explicit URL, otherwise Render's automatically injected service URL.
    public_base_url: str = (
        os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    )
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "").strip()
    text_model: str = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.7-flash").strip()
    image_model: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image").strip()
    memory_size: int = env_int("CHAT_MEMORY_SIZE", 40, 10)
    memory_ttl_seconds: int = env_int("CHAT_MEMORY_TTL_SECONDS", 7200, 60)
    image_pool_ttl_seconds: int = env_int("IMAGE_POOL_TTL_SECONDS", 21600, 300)
    min_cooldown_seconds: int = env_int("MIN_COOLDOWN_SECONDS", 20, 1)
    max_cooldown_seconds: int = env_int("MAX_COOLDOWN_SECONDS", 45, 1)
    soft_hourly_limit: int = env_int("SOFT_HOURLY_LIMIT", 20, 1)
    hard_hourly_limit: int = env_int("HARD_HOURLY_LIMIT", 30, 1)
    max_consecutive_bot_messages: int = env_int("MAX_CONSECUTIVE_BOT_MESSAGES", 2, 1)
    max_action_payload_chars: int = env_int("MAX_ACTION_PAYLOAD_CHARS", 1200, 100)
    max_image_mb: int = env_int("MAX_IMAGE_MB", 8, 1)
    enabled_chaos: bool = env_bool("ENABLED_CHAOS", True)
    enabled_moderation: bool = env_bool("ENABLED_MODERATION", True)
    enabled_games: bool = env_bool("ENABLED_GAMES", True)
    enabled_proactive: bool = env_bool("ENABLED_PROACTIVE", True)
    ai_min_score: int = env_int("AI_MIN_SCORE", 34, 0)
    callback_min_age_seconds: int = env_int("CALLBACK_MIN_AGE_SECONDS", 300, 60)
    proactive_quiet_seconds: int = env_int("PROACTIVE_QUIET_SECONDS", 600, 60)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    companion_bot_tokens: tuple[str, ...] = field(default_factory=lambda: tuple(x.strip() for x in os.getenv("COMPANION_BOT_TOKENS", "").split(",") if x.strip()))
    defaults: PersonalityDefaults = field(default_factory=PersonalityDefaults)


settings = Settings()
