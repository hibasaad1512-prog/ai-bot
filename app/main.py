from __future__ import annotations
import hashlib, hmac, logging, os
from flask import Flask, request, abort
import telebot
from app.config import settings
from app.telegram.bot import KyoosBot

logging.basicConfig(level=getattr(logging,settings.log_level,logging.INFO),format="%(asctime)s %(levelname)s %(name)s %(message)s")
log=logging.getLogger("kyoos")
app=Flask(__name__)

_kyoos:KyoosBot|None=None

def bot_instance():
    global _kyoos
    if _kyoos is None:_kyoos=KyoosBot()
    return _kyoos

@app.get("/")
@app.get("/health")
def health():
    return {"status":"ok","service":"KYOOS CHAOS AI","gemini":bool(settings.gemini_api_key)}

@app.post("/telegram/webhook")
def telegram_webhook():
    secret=request.headers.get("X-Telegram-Bot-Api-Secret-Token","")
    expected=settings.webhook_secret
    if expected and not hmac.compare_digest(secret,expected):abort(403)
    if not request.is_json:abort(400)
    try:
        update=telebot.types.Update.de_json(request.get_data(as_text=True)); bot_instance().process(update); return {"ok":True}
    except Exception:log.exception("webhook failure"); abort(500)

@app.get("/debug")
def debug():
    return {"ok":True,"gemini":bot_instance().runtime.ai.enabled}

@app.cli.command("set-webhook")
def set_webhook():
    b=bot_instance().bot
    if not settings.public_base_url:raise SystemExit("PUBLIC_BASE_URL required")
    url=f"{settings.public_base_url}/telegram/webhook"; b.set_webhook(url=url,secret_token=settings.webhook_secret or None); print(url)

if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
