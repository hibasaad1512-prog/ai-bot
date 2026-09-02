from __future__ import annotations

import hmac
import logging
import os
import threading
import time

from flask import Flask, abort, request

import requests
import telebot

from app.config import settings
from app.telegram.bot import KyoosBot
from app.ai.fast_patch import install as install_fast_groq

install_fast_groq()

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
    bot = bot_instance()
    return {
        "status": "ok",
        "service": "KYOOS CHAOS AI",
        "telegram": bool(bot.token),
        "groq": bot.runtime.ai.enabled,
        "webhook_base": bool(settings.public_base_url),
    }


def _process_update(raw_body: str) -> None:
    """Process Telegram updates outside the HTTP request."""
    try:
        update = telebot.types.Update.de_json(raw_body)
        bot_instance().process(update)
    except Exception:
        log.exception("background webhook processing failed")


@app.post("/telegram/webhook")
def telegram_webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = settings.webhook_secret
    if expected and not hmac.compare_digest(secret, expected):
        abort(403)
    if not request.is_json:
        abort(400)

    raw_body = request.get_data(as_text=True)
    threading.Thread(
        target=_process_update,
        args=(raw_body,),
        daemon=True,
        name="telegram-update",
    ).start()
    return {"ok": True}


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


def _keepalive_loop() -> None:
    """Keep the free Render instance warm enough for scheduled behavior."""
    if os.getenv("KEEPALIVE_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    base = settings.public_base_url
    if not base:
        return
    interval = max(300, int(os.getenv("KEEPALIVE_INTERVAL_SECONDS", "600")))
    time.sleep(60)
    while True:
        try:
            requests.get(f"{base}/", timeout=8)
        except Exception:
            log.debug("keepalive ping failed", exc_info=True)
        time.sleep(interval)


threading.Thread(target=_keepalive_loop, daemon=True, name="render-keepalive").start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
