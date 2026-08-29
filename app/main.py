from __future__ import annotations

import hmac
import logging
import os

from flask import Flask, abort, request

import telebot

from app.config import settings
from app.telegram.bot import KyoosBot

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("kyoos")
app = Flask(__name__)

_kyoos: KyoosBot | None = None


def bot_instance() -> KyoosBot:
    global _kyoos
    if _kyoos is None:
        _kyoos = KyoosBot()
    return _kyoos


@app.get("/")
@app.get("/health")
def health():
    # IMPORTANT: do not return health before initializing the Telegram bot.
    # Render hits this endpoint, and this is what triggers webhook registration.
    bot = bot_instance()
    return {
        "status": "ok",
        "service": "KYOOS CHAOS AI",
        "telegram": bool(bot.token),
        "groq": bot.runtime.ai.enabled,
        "webhook_base": bool(settings.public_base_url),
    }


@app.post("/telegram/webhook")
def telegram_webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = settings.webhook_secret
    if expected and not hmac.compare_digest(secret, expected):
        abort(403)
    if not request.is_json:
        abort(400)

    try:
        update = telebot.types.Update.de_json(request.get_data(as_text=True))
        bot_instance().process(update)
        return {"ok": True}
    except Exception:
        log.exception("webhook failure")
        abort(500)


@app.get("/debug")
def debug():
    bot = bot_instance()
    return {
        "ok": True,
        "groq": bot.runtime.ai.enabled,
        "model": settings.groq_text_model,
        "webhook": bool(settings.public_base_url),
    }


@app.cli.command("set-webhook")
def set_webhook():
    b = bot_instance().bot
    if not settings.public_base_url:
        raise SystemExit("PUBLIC_BASE_URL required")
    url = f"{settings.public_base_url}/telegram/webhook"
    b.set_webhook(url=url, secret_token=settings.webhook_secret or None)
    print(url)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
