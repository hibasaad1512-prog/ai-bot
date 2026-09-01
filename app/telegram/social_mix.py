from __future__ import annotations

import random
import logging

from app.telegram.permissions import is_group

log = logging.getLogger(__name__)

# Deliberately short, natural fallbacks. These are used only for the local/random
# side of the social mix; normal AI replies still use the existing handler.
RANDOM_REPLIES = (
    "ههههه شنو هاد 😂",
    "واش بصح؟ 😭",
    "الميرفاوية كتراقب بصمت 👀",
    "آه لا لا 😹",
    "شنو كتخربقو تما؟",
    "مزيان هادي 😂",
    "أنا ما شفت والو… 👀",
    "mrrp 😼",
    "واخااا 😭",
    "هادشي خرج على السيطرة شوية 😹",
    "hmm… interesting 👀",
    "meow.",
)


def install(handlers) -> None:
    """Add a local/random branch in front of the existing AI path.

    The original handler remains untouched. Roughly 30% of eligible group text
    messages become an instant local reply; the other 70% continue to the
    existing AI pipeline. This keeps Merva from feeling like every message is
    an API call while preserving the full conversation-aware AI behavior.
    """
    original = handlers.on_message

    def wrapped(message):
        try:
            if (
                getattr(message, "from_user", None)
                and is_group(getattr(message.chat, "type", ""))
                and not getattr(message.from_user, "is_bot", False)
                and bool((getattr(message, "text", None) or "").strip())
                and not (message.text or "").lstrip().startswith("/")
                and random.random() < 0.30
            ):
                reply = random.choice(RANDOM_REPLIES)
                handlers.bot.send_message(
                    message.chat.id,
                    reply,
                    reply_to_message_id=message.message_id,
                    allow_sending_without_reply=True,
                )
                try:
                    handlers._remember_bot_reply(
                        message,
                        reply,
                        message.message_id,
                    )
                except Exception:
                    log.exception("could not remember local random reply")
                return
        except Exception:
            log.exception("local social mix failed; falling back to AI")
        return original(message)

    handlers.on_message = wrapped
